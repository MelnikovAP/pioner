"""Record-from-arm: stream raw AI off the persistent ring to HDF5 (P1-17).

A :class:`DiskRecorder` is a ring *consumer* that drains the persistent AI scan
**straight to an extendable HDF5 dataset** between ``start`` (pressed at
experiment **arm**) and ``stop`` (experiment end or abort), and marks the sample
index where the experiment proper begins (``mark_start`` at experiment
**start**). Because each drained chunk is appended to disk and dropped, host
memory stays flat regardless of run length -- so multi-hour / multi-day slow and
finite-iso runs do not accumulate gigabytes of samples in RAM (the design
requirement that motivated streaming over the earlier in-memory buffer).

The recorded file holds one ``raw_ai`` dataset of shape ``(rows, channels)`` plus
attributes ``mark_index`` (baseline|run boundary, -1 if never marked) and
``rows``. Calibration (``apply_calibration``) and the final ``exp_data.h5``
layout (``save_run_to_h5``) are produced by the caller at finalise time, reading
this raw file back -- they need the mode's programs / voltage profiles, which the
recorder does not own. Wiring into slow / finite-iso lands in P1-17 steps 4 / 5.

Mechanics. The persistent ring exposes a single, *destructive* per-consumer
cursor: each ``read_new_samples`` returns everything appended since that
consumer's previous call and advances the cursor. So:

* every read + append runs under one lock -- draining is serialized, so two
  callers (the background thread, ``mark_start``, ``stop``) never split a delta
  across two appends out of order, and HDF5 (not thread-safe) is only ever
  touched by one thread at a time.
* we **prime** the cursor at ``start`` (``reset_ring_cursor`` then one discarded
  ``read_new_samples``) so capture begins at arm, not at the trailing backlog.
* the ring is sized to ``ring_max_seconds``; a background thread drains every
  ``poll_interval`` (well under the ring depth) so a long run does not overflow
  the ring between the explicit ``mark_start`` / ``stop`` drains.

No samples are lost as long as the drain keeps up with the ring: HDF5 extendable
appends are exact and order-preserving (verified), and ``mark_start`` / ``stop``
each drain explicitly, so the mark always lands at the true baseline|run
boundary. (Keeping up on real hardware -- the ring not overflowing at the chosen
rate -- is the separate HW soak item, P1-17 step 4c.)
"""

from __future__ import annotations

import logging
import threading
from typing import Optional, Protocol

import h5py
import numpy as np

logger = logging.getLogger(__name__)


class RingSource(Protocol):
    """Minimal ring interface the recorder needs (``ExperimentManager`` satisfies it)."""

    def reset_ring_cursor(self, consumer_id: str) -> None: ...

    def read_new_samples(self, consumer_id: str) -> np.ndarray: ...


class DiskRecorder:
    """Stream the persistent AI ring to an HDF5 file from arm to stop (P1-17).

    Parameters
    ----------
    ring
        Object exposing ``reset_ring_cursor`` / ``read_new_samples`` (the
        in-process :class:`ExperimentManager`).
    h5_path
        Destination HDF5 file (overwritten on ``start``). Holds a single
        extendable ``raw_ai`` dataset plus ``mark_index`` / ``rows`` attributes.
    consumer_id
        Private cursor key on the ring. Must not collide with other consumers
        (the live plot, the iso-streaming cursor, ...).
    poll_interval
        Seconds between background drains. Keep well below the ring's
        ``ring_max_seconds`` so the ring never overwrites un-captured samples.
    dataset
        Name of the raw dataset inside the file.
    """

    def __init__(
        self,
        ring: RingSource,
        h5_path: str,
        consumer_id: str = "disk_recorder",
        poll_interval: float = 0.2,
        dataset: str = "raw_ai",
    ) -> None:
        self._ring = ring
        self._path = str(h5_path)
        self._consumer_id = str(consumer_id)
        self._poll_interval = float(poll_interval)
        self._dataset_name = str(dataset)
        self._rows: int = 0
        self._mark: Optional[int] = None
        # One lock guards read+append (serialises drains so chunk order is kept)
        # and every HDF5 access (h5py is not thread-safe) plus _rows / _mark.
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._h5: Optional[h5py.File] = None
        self._dset: Optional[h5py.Dataset] = None

    # -- introspection -------------------------------------------------
    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def mark_index(self) -> Optional[int]:
        """Row where the experiment proper begins (None until ``mark_start``)."""
        with self._lock:
            return self._mark

    @property
    def rows(self) -> int:
        """Rows captured so far."""
        with self._lock:
            return self._rows

    @property
    def path(self) -> str:
        return self._path

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        """Begin recording from arm: open the file, prime the cursor, drain."""
        if self.is_recording:
            logger.warning("DiskRecorder.start called while already recording; ignoring")
            return
        with self._lock:
            self._rows = 0
            self._mark = None
            self._h5 = h5py.File(self._path, "w")
            self._dset = None  # created on the first non-empty chunk
            # Prime so capture starts at arm, not at the trailing backlog:
            # reset clears any stale cursor, the discarded read sets it to head.
            self._ring.reset_ring_cursor(self._consumer_id)
            self._ring.read_new_samples(self._consumer_id)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="disk-recorder", daemon=True
        )
        self._thread.start()
        logger.info(
            "DiskRecorder started -> %s (consumer=%s, poll=%.3fs)",
            self._path, self._consumer_id, self._poll_interval,
        )

    def mark_start(self) -> None:
        """Mark the current position as experiment t=0 (baseline|run boundary).

        Drains everything available up to now first, under the lock, so the
        mark lands exactly after the last pre-start sample regardless of the
        background thread.
        """
        with self._lock:
            self._drain_locked()
            self._mark = self._rows
        logger.info("DiskRecorder mark_start at row %d", self._mark)

    def stop(self) -> str:
        """Stop draining, finalise the file, return its path.

        The raw samples live in the ``raw_ai`` dataset; ``mark_index`` / ``rows``
        are stored as dataset attributes for the finalise (calibration) step.
        """
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self._drain_locked()  # final drain
            if self._h5 is not None:
                if self._dset is not None:
                    self._dset.attrs["mark_index"] = (
                        -1 if self._mark is None else int(self._mark)
                    )
                    self._dset.attrs["rows"] = int(self._rows)
                # Always record the boundary at file level too, so a zero-row
                # recording still carries its (empty) metadata.
                self._h5.attrs["mark_index"] = (
                    -1 if self._mark is None else int(self._mark)
                )
                self._h5.attrs["rows"] = int(self._rows)
                self._h5.flush()
                self._h5.close()
                self._h5 = None
                self._dset = None
        logger.info("DiskRecorder stopped: %d rows (mark=%s) -> %s",
                    self._rows, self._mark, self._path)
        return self._path

    # -- internals -----------------------------------------------------
    def _drain_locked(self) -> int:
        """Read the pending delta and append it to disk. Caller holds ``self._lock``."""
        chunk = self._ring.read_new_samples(self._consumer_id)
        if chunk.size == 0:
            return 0
        n = int(chunk.shape[0])
        if self._h5 is None:
            return 0  # stopped/closed: drop late samples rather than crash
        if self._dset is None:
            n_channels = int(chunk.shape[1])
            self._dset = self._h5.create_dataset(
                self._dataset_name,
                shape=(0, n_channels),
                maxshape=(None, n_channels),
                chunks=True,
                dtype="float64",
            )
        self._dset.resize(self._rows + n, axis=0)
        self._dset[self._rows:self._rows + n] = chunk
        self._rows += n
        return n

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._drain_locked()
            except Exception:
                logger.exception("DiskRecorder drain failed")
            self._stop.wait(self._poll_interval)


__all__ = ["DiskRecorder", "RingSource"]
