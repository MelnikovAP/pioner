"""Record-from-arm: capture raw AI off the persistent ring (P1-17, step 2).

A :class:`DiskRecorder` is a ring *consumer* that drains the persistent AI scan
into an in-memory buffer between ``start`` (pressed at experiment **arm**) and
``stop`` (experiment end or abort), and marks the sample index where the
experiment proper begins (``mark_start`` at experiment **start**). The assembled
raw frame plus that mark let the caller split the pre-start baseline from the
run and calibrate the whole thing at finalise.

Scope (this module): **raw capture only**. Calibration (``apply_calibration``)
and the HDF5 write (``save_run_to_h5``) are done by the caller at finalise time,
using :pyattr:`raw` and :pyattr:`mark_index` -- they need the mode's programs /
voltage profiles, which the recorder does not own. Wiring into slow / finite-iso
lands in P1-17 steps 4 / 5.

Mechanics. The persistent ring exposes a single, *destructive* per-consumer
cursor: each ``read_new_samples`` returns everything appended since that
consumer's previous call and advances the cursor. So:

* draining must be **serialized** -- two concurrent reads on the same consumer
  would split a delta across two appends in arbitrary order. A single lock is
  held across each read + append, so chunk order is always preserved.
* we **prime** the cursor at ``start`` (``reset_ring_cursor`` then one discarded
  ``read_new_samples``) so capture begins at arm, not at the trailing ring
  backlog.
* the ring is sized to ``ring_max_seconds``; a background thread drains every
  ``poll_interval`` (well under the ring depth) so a long run does not overflow
  the ring between the explicit ``mark_start`` / ``stop`` drains.

Correctness does not depend on the thread's timing: ``mark_start`` and ``stop``
each perform their own drain, so every sample is captured by the thread,
``mark_start``, or the final ``stop`` drain, and the mark always lands exactly
at the baseline|run boundary.
"""

from __future__ import annotations

import logging
import threading
from typing import List, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class RingSource(Protocol):
    """Minimal ring interface the recorder needs (``ExperimentManager`` satisfies it)."""

    def reset_ring_cursor(self, consumer_id: str) -> None: ...

    def read_new_samples(self, consumer_id: str) -> np.ndarray: ...


class DiskRecorder:
    """Drain the persistent AI ring into memory from arm to stop (P1-17).

    Parameters
    ----------
    ring
        Object exposing ``reset_ring_cursor`` / ``read_new_samples`` (the
        in-process :class:`ExperimentManager`).
    consumer_id
        Private cursor key on the ring. Must not collide with other consumers
        (e.g. the live plot or the iso-streaming cursor).
    poll_interval
        Seconds between background drains. Keep well below the ring's
        ``ring_max_seconds`` so the ring never overwrites un-captured samples.
    """

    def __init__(
        self,
        ring: RingSource,
        consumer_id: str = "disk_recorder",
        poll_interval: float = 0.2,
    ) -> None:
        self._ring = ring
        self._consumer_id = str(consumer_id)
        self._poll_interval = float(poll_interval)
        self._chunks: List[np.ndarray] = []
        self._rows: int = 0
        self._mark: Optional[int] = None
        # One lock guards the whole read+append (serialises drains so chunk
        # order is preserved) and the _rows / _mark / _chunks fields.
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

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

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        """Begin recording from arm: prime the cursor at head, start draining."""
        if self.is_recording:
            logger.warning("DiskRecorder.start called while already recording; ignoring")
            return
        with self._lock:
            self._chunks = []
            self._rows = 0
            self._mark = None
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
            "DiskRecorder started (consumer=%s, poll=%.3fs)",
            self._consumer_id, self._poll_interval,
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

    def stop(self) -> np.ndarray:
        """Stop draining and return the assembled raw frame ``(rows, channels)``."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self._drain_locked()  # final drain
            raw = (
                np.concatenate(self._chunks, axis=0)
                if self._chunks
                else np.empty((0, 0), dtype=float)
            )
            mark = self._mark
        logger.info("DiskRecorder stopped: %d rows (mark=%s)", raw.shape[0], mark)
        return raw

    # -- internals -----------------------------------------------------
    def _drain_locked(self) -> int:
        """Read the pending delta and append it. Caller holds ``self._lock``."""
        chunk = self._ring.read_new_samples(self._consumer_id)
        if chunk.size == 0:
            return 0
        self._chunks.append(chunk)
        self._rows += int(chunk.shape[0])
        return int(chunk.shape[0])

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._drain_locked()
            except Exception:
                logger.exception("DiskRecorder drain failed")
            self._stop.wait(self._poll_interval)


__all__ = ["DiskRecorder", "RingSource"]
