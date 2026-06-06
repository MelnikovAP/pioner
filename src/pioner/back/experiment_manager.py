"""High-level orchestration of an AO + AI scan.

The experiment manager owns the lifecycle of a single experiment and exposes
three public entry points:

* :meth:`finite_scan`  — run a paced AO profile while continuously sampling
  AI for the duration of the AO buffer. Used by both *fast* and *slow*
  modes; data is written to disk in 0.5 s buffer chunks and then merged.
* :meth:`iso_scan`     — apply a static AO voltage on one channel (or push a
  modulated AC profile in CONTINUOUS mode) and stream AI samples into a
  ring buffer in a background thread. The caller can stop the scan at any
  moment and grab a snapshot of the most recent samples without losing
  points.
* :meth:`stop`         — abort whatever is currently running.

Implementation notes
--------------------
* AI is paced ``CONTINUOUS`` for slow/iso (drain a 1 s buffer via the
  half-buffer flip, stop cleanly at any time), but fast-heat uses a single-shot
  ``DEFAULTIO`` scan with a full-length buffer read once at the end -- no drain
  race, hence no FIFO ``OVERRUN`` (todo P1-30).
* For the CONTINUOUS path the AI buffer is sized to exactly **one second** of
  data. The reader loop
  flips between the lower and upper half of the buffer based on the actual
  ``current_index`` returned by the driver, which makes it robust against
  slow callers (we will detect a "skipped" half by index comparison and
  copy both halves before re-arming).
* For finite scans we wait for the AO scan to terminate before stopping AI,
  then drain whatever was still in the AI buffer.
* Data on disk goes through ``pandas.HDFStore``; we trigger the lazy
  initialisation of ``to_hdf`` once at startup so that the first acquisition
  buffer is not lost to the ~1 s setup delay.
"""

from __future__ import annotations

import glob
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

from .mock_uldaq import uldaq as ul
from pioner.shared.constants import (
    BUFFER_DUMMY_1,
    RAW_DATA_BUFFER_FILE_FORMAT,
    RAW_DATA_BUFFER_FILE_PREFIX,
    RAW_DATA_FILE_REL_PATH,
    RAW_DATA_FOLDER_REL_PATH,
)
from pioner.shared.settings import BackSettings
from pioner.back.ai_device import AiDeviceHandler, AiParams
from pioner.back.ao_data_generators import ScanDataGenerator
from pioner.back.ao_device import AoDeviceHandler, AoParams
from pioner.back.daq_device import DaqDeviceHandler

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a finite scan: per-channel AI samples and the actual scan rate."""

    data: pd.DataFrame
    ai_rate: float
    ao_rate: float
    samples_per_channel: int


class ExperimentManager:
    """Owns a single AO/AI run and the associated on-disk artefacts."""

    def __init__(self, daq_device_handler: DaqDeviceHandler, settings: BackSettings):
        self._daq_device_handler = daq_device_handler
        self._ai_params: AiParams = settings.ai_params
        self._ao_params: AoParams = settings.ao_params

        self._ai_handler: Optional[AiDeviceHandler] = None
        self._ao_handler: Optional[AoDeviceHandler] = None
        self._ao_buffer: Optional[Sequence[float]] = None
        self._ai_buffer_samples_per_channel: int = 0

        # Cooperative cancel for a finite_scan in flight (P1-17 step 3). Set by
        # ``request_stop`` (e.g. from a GUI Stop button on another thread); the
        # collect loops poll it and break, then finite_scan zeroes AO.
        self._cancel = threading.Event()

        # Background ring-buffer worker (used by iso_scan and the
        # AIProvider live-streaming layer).
        self._ring_thread: Optional[threading.Thread] = None
        self._ring_stop = threading.Event()
        self._ring_lock = threading.Lock()
        self._ring_data: deque[np.ndarray] = deque()
        self._ring_max_seconds: float = 10.0
        # Total samples ever appended to the ring buffer (monotonic counter,
        # incremented in ``_ring_loop``). Used as the cursor space for
        # ``read_new_samples``.
        self._ring_total_samples: int = 0
        # Per-consumer cursors for ``read_new_samples`` -- maps an opaque
        # consumer id to the value of ``_ring_total_samples`` at the time of
        # its last successful read. Guarded by ``_ring_lock``.
        self._ring_cursors: dict[str, int] = {}

        self._prime_pandas()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "ExperimentManager":
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        try:
            self.stop()
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logger.error("Error during experiment cleanup: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Disk preparation (carried over from the historical implementation)
    # ------------------------------------------------------------------
    @staticmethod
    def _prime_pandas() -> None:
        """Warm up pandas' HDF subsystem once and clean previous artefacts."""
        os.makedirs(RAW_DATA_FOLDER_REL_PATH, exist_ok=True)
        try:
            pd.DataFrame([]).to_hdf(
                RAW_DATA_FILE_REL_PATH, key="dataset", format="table", mode="w"
            )
        except Exception as exc:
            logger.debug("Pandas prime write failed (likely no PyTables): %s", exc)

        pattern = os.path.join(
            RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_PREFIX + "*.h5"
        )
        for fpath in glob.glob(pattern):
            try:
                os.remove(fpath)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Device handler lazy initialisation
    # ------------------------------------------------------------------
    def _ensure_ao_handler(self) -> AoDeviceHandler:
        if self._ao_handler is None:
            self._ao_handler = AoDeviceHandler(
                self._daq_device_handler.get_ao_device(), self._ao_params
            )
        return self._ao_handler

    def _ensure_ai_handler(self, samples_per_channel: int) -> AiDeviceHandler:
        if self._ai_handler is None:
            self._ai_handler = AiDeviceHandler(
                self._daq_device_handler.get_ai_device(), self._ai_params
            )
        if self._ai_handler.samples_per_channel != samples_per_channel:
            self._ai_handler.allocate_buffer(samples_per_channel)
        self._ai_buffer_samples_per_channel = samples_per_channel
        return self._ai_handler

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def finite_scan(
        self,
        voltage_profiles: dict,
        ai_channels: Sequence[int],
        seconds: float,
        single_shot: bool = False,
    ) -> ScanResult:
        """Run a finite paced AO + AI experiment.

        ``voltage_profiles`` is an iterable per-channel array of floats with
        length ``round(seconds * sample_rate)``. ``ai_channels`` is the subset
        of AI channels to keep in the resulting DataFrame. ``seconds`` may be
        fractional.

        Two AI collection strategies:

        * ``single_shot=False`` (default, used by slow): AI runs ``CONTINUOUS``
          into a one-second buffer and the host drains it with the half-buffer
          flip; the frame is trimmed to the exact sample count.
        * ``single_shot=True`` (used by fast-heat): AI runs ``DEFAULTIO`` into a
          host buffer sized to the **whole** scan; the DAQ DMAs everything and
          the host reads once at the end. No half-buffer drain race means no
          FIFO ``OVERRUN`` -- the IR-branch fix for the fast-heat crash class
          (todo P1-30 / postmortem 2026-05-23-fifo-overrun-continuous-ai).
        """
        if seconds <= 0:
            raise ValueError("seconds must be > 0")
        if not voltage_profiles:
            raise ValueError("voltage_profiles is empty")

        # Fresh cancel state for this scan (a stale set() from a prior aborted
        # run must not abort this one before it starts).
        self._cancel.clear()

        total_samples = int(round(self._ai_params.sample_rate * seconds))
        # Single-shot sizes the AI buffer to the full scan (DEFAULTIO, read once
        # at the end); the CONTINUOUS path keeps the 1 s half-flip buffer.
        ai_buffer_spc = total_samples if single_shot else self._ai_params.sample_rate
        ai_handler = self._ensure_ai_handler(ai_buffer_spc)
        ao_handler = self._ensure_ao_handler()

        # Configure AO for finite output; AI stays continuous. When
        # ``hardware_trigger`` is enabled (todo P0-5) both scans pre-arm with
        # ``EXTTRIGGER`` and only start when ``fire_software_trigger`` is
        # called, so they share a single t=0 clock edge instead of the
        # ~100 us start skew we get from sequential ``scan()`` calls.
        #
        # Real-hardware fallbacks if ``EXTTRIGGER`` does not behave as
        # expected on the production board (validate with the loopback test:
        # drive a 1 kHz square wave on AO ch1, read it back on AI ch1, look
        # for the leading edge — should be within 1 sample of t=0):
        #   1) External pacer-clock sharing — wire the AO scan clock output
        #      (XDPCR) on USB-2637 to the AI external clock input (XAPCR);
        #      arm AO with ``ScanOption.PACEROUT`` and AI with
        #      ``ScanOption.EXTCLOCK``. Needs one physical jumper, no
        #      software trigger. Note that USB-2637 has no internal shared
        #      pacer (AO and AI pacers are independent by design — see
        #      docs/design-notes.md and specs/USB-2637.pdf), so the external
        #      jumper is mandatory for clock-level sync.
        #   2) Software offset: measure the persistent skew once, store it
        #      as ``calibration.pre_trigger_samples``, and trim the leading
        #      ``N`` samples in ``apply_calibration``. Cheap but host-specific.
        triggered = bool(getattr(self._daq_device_handler._params,
                                  "hardware_trigger", False))
        ao_options = ul.ScanOption.BLOCKIO
        ai_options = ul.ScanOption.DEFAULTIO if single_shot else ul.ScanOption.CONTINUOUS
        if triggered:
            ao_options |= ul.ScanOption.EXTTRIGGER
            ai_options |= ul.ScanOption.EXTTRIGGER
        self._ao_params.options = ao_options
        self._ai_params.options = ai_options

        ao_buffer: Sequence[float] = ScanDataGenerator(
            voltage_profiles,
            self._ao_params.low_channel,
            self._ao_params.high_channel,
        ).get_buffer()
        self._ao_buffer = ao_buffer

        # Stop any leftover scans before starting fresh ones.
        ao_handler.stop()
        ai_handler.stop()

        # Without a trigger we still arm AI first so we don't miss the
        # leading edge of AO; with a trigger the order does not matter
        # because neither scan progresses until fire_software_trigger().
        ai_rate = ai_handler.scan(self._ai_buffer_samples_per_channel)
        ao_rate = ao_handler.scan(ao_buffer)
        if triggered:
            self._daq_device_handler.fire_software_trigger()

        if single_shot:
            df = self._collect_finite_ai_single_shot(
                ai_handler, total_samples, ai_channels, seconds
            )
        else:
            df = self._collect_finite_ai(ai_handler, ao_handler, seconds, ai_channels)

        ao_handler.stop()
        ai_handler.stop()

        # On a cooperative abort (request_stop) the scan stop above only halts
        # the pacer; the DAC holds its last sample. Drive AO to 0 so the heater
        # is never left powered after a Stop (P1-17 step 3 / heater-safety rule).
        if self._cancel.is_set():
            self.zero_ao()
            logger.info("finite_scan cancelled; AO driven to 0 V")

        return ScanResult(
            data=df,
            ai_rate=float(ai_rate),
            ao_rate=float(ao_rate),
            samples_per_channel=int(round(ai_rate * seconds)),
        )

    def request_stop(self) -> None:
        """Cooperatively abort a finite_scan in flight (P1-17 step 3).

        Sets the cancel flag the collect loops poll. Safe to call from another
        thread (e.g. a GUI Stop button) while ``finite_scan`` runs; the loop
        breaks, the scan stops, and AO is zeroed. No-op if nothing is running.
        """
        self._cancel.set()

    def ao_set(self, channel: int, voltage: float) -> None:
        """Hold a static voltage on a single AO channel (iso primitive)."""
        ao_handler = self._ensure_ao_handler()
        ao_handler.set_voltage(channel, voltage)

    def ao_modulated(self, voltage_profiles: dict) -> None:
        """Drive a continuous AO profile (used by iso/slow with modulation).

        When ``BackSettings.daq_params.hardware_trigger`` is on, pre-arm the
        AO scan with ``EXTTRIGGER``. The matching AI side is armed by
        :meth:`start_ring_buffer`, which fires the shared trigger once both
        scans are idle on the trigger gate.
        """
        ao_handler = self._ensure_ao_handler()
        triggered = bool(getattr(self._daq_device_handler._params,
                                  "hardware_trigger", False))
        ao_options = ul.ScanOption.CONTINUOUS
        if triggered:
            ao_options |= ul.ScanOption.EXTTRIGGER
        self._ao_params.options = ao_options
        ao_buffer: Sequence[float] = ScanDataGenerator(
            voltage_profiles,
            self._ao_params.low_channel,
            self._ao_params.high_channel,
        ).get_buffer()
        self._ao_buffer = ao_buffer
        ao_handler.stop()
        ao_handler.scan(ao_buffer)

    def start_ring_buffer(
        self,
        ai_channels: Sequence[int],
        max_seconds: float = 10.0,
    ) -> None:
        """Start streaming AI into a background ring buffer.

        ``ai_channels`` is the subset to retain. ``max_seconds`` is the depth
        of history kept in memory; older samples are dropped as new ones
        arrive. Use :meth:`snapshot_ring_buffer` to read the latest samples,
        and :meth:`stop_ring_buffer` to stop the worker thread.
        """
        if self._ring_thread is not None and self._ring_thread.is_alive():
            raise RuntimeError("Ring buffer is already running")

        # Same constraint as ``_collect_finite_ai``: the half-buffer reshape
        # requires an even ``samples_per_channel``.
        if self._ai_params.sample_rate % 2 != 0:
            raise ValueError(
                f"AI sample_rate must be even (got {self._ai_params.sample_rate}); "
                "the half-buffer flip protocol requires an even buffer length."
            )
        # If a previous ``ao_modulated`` armed AO with ``EXTTRIGGER`` (because
        # ``hardware_trigger`` is on), arm AI the same way and fire the shared
        # trigger after both scans are gated. This gives iso AC a clean t=0 on
        # both AO and AI, matching what ``finite_scan`` does for fast/slow.
        # For DC iso (``ao_set``) AO is not a scan, so we never set
        # ``EXTTRIGGER`` on AI: there is nothing to synchronise with.
        ao_triggered = bool(self._ao_params.options & ul.ScanOption.EXTTRIGGER)
        ai_options = ul.ScanOption.CONTINUOUS
        if ao_triggered:
            ai_options |= ul.ScanOption.EXTTRIGGER
        self._ai_params.options = ai_options
        ai_handler = self._ensure_ai_handler(self._ai_params.sample_rate)
        ai_handler.stop()
        ai_handler.scan(self._ai_buffer_samples_per_channel)
        if ao_triggered:
            self._daq_device_handler.fire_software_trigger()

        self._ring_max_seconds = float(max_seconds)
        with self._ring_lock:
            self._ring_data.clear()
            # New scan: reset the monotonic sample counter and any stale
            # consumer cursors from a previous session.
            self._ring_total_samples = 0
            self._ring_cursors.clear()
        self._ring_stop.clear()
        self._ring_thread = threading.Thread(
            target=self._ring_loop,
            args=(ai_handler, list(ai_channels)),
            name="AiRingBuffer",
            daemon=True,
        )
        self._ring_thread.start()

    def stop_ring_buffer(self) -> None:
        self._ring_stop.set()
        if self._ring_thread is not None:
            self._ring_thread.join(timeout=2.0)
            self._ring_thread = None
        if self._ai_handler is not None:
            self._ai_handler.stop()

    def snapshot_ring_buffer(self) -> np.ndarray:
        """Return a copy of all samples currently held in the ring buffer."""
        with self._ring_lock:
            if not self._ring_data:
                return np.empty((0, 0), dtype=float)
            return np.concatenate(list(self._ring_data), axis=0)

    # ------------------------------------------------------------------
    # Ring buffer extensions for the AIProvider layer.
    #
    # Two access patterns coexist:
    # * UI live display (Values sidebar, slow-heat plot): wants "give me the
    #   most recent N samples to compute a sliding-window demod" -- use
    #   ``peek_last_samples``.
    # * Disk recorder / mode finalisers: want "give me everything new since
    #   my last call" -- use ``read_new_samples`` with a per-consumer
    #   cursor.
    #
    # Cursors are expressed in terms of total samples ever appended to the
    # ring buffer (``_ring_total_samples``). That counter is incremented in
    # ``_ring_loop`` as each half-buffer is copied into ``_ring_data``.
    # Samples that have already fallen off the front of the deque (because
    # ``max_chunks`` was exceeded) are gone -- a consumer that fell that
    # far behind sees the gap reported as ``samples_lost`` in the metadata
    # of the next ``read_new_samples`` call.
    # ------------------------------------------------------------------
    def peek_last_samples(self, samples: int) -> np.ndarray:
        """Return the most recent ``samples`` rows from the ring buffer.

        Read-only: no cursor is advanced. If fewer than ``samples`` rows
        are available, returns whatever is in the ring (possibly empty).
        """
        if samples <= 0:
            return np.empty((0, 0), dtype=float)
        with self._ring_lock:
            if not self._ring_data:
                return np.empty((0, 0), dtype=float)
            collected: List[np.ndarray] = []
            remaining = int(samples)
            # Walk chunks from the back (newest) to the front, take the
            # tail of each as needed.
            for chunk in reversed(self._ring_data):
                if remaining <= 0:
                    break
                take = min(len(chunk), remaining)
                collected.append(chunk[-take:])
                remaining -= take
            collected.reverse()
            return np.concatenate(collected, axis=0)

    def read_new_samples(self, consumer_id: str) -> np.ndarray:
        """Return everything appended since this consumer's previous call.

        Advances the consumer's private cursor. First call for a given
        ``consumer_id`` returns whatever is currently in the ring buffer
        (the consumer effectively "joins" at the current head).
        """
        with self._ring_lock:
            head = int(self._ring_total_samples)
            last_seen = self._ring_cursors.get(consumer_id)
            if last_seen is None:
                # First read for this consumer: start from the oldest
                # sample currently in the ring.
                start = head - self._ring_buffered_samples_locked()
            else:
                start = int(last_seen)
            # If the consumer fell behind further than the ring holds,
            # the oldest still-available sample is the best we can do.
            oldest_available = head - self._ring_buffered_samples_locked()
            samples_lost = max(0, oldest_available - start)
            start = max(start, oldest_available)
            if start >= head:
                self._ring_cursors[consumer_id] = head
                return np.empty((0, 0), dtype=float)

            # Walk chunks from the front. Need to skip ``start - oldest_available``
            # rows from the head of the visible ring.
            skip = max(0, start - oldest_available)
            collected: List[np.ndarray] = []
            for chunk in self._ring_data:
                if skip >= len(chunk):
                    skip -= len(chunk)
                    continue
                if skip > 0:
                    collected.append(chunk[skip:])
                    skip = 0
                else:
                    collected.append(chunk)
            self._ring_cursors[consumer_id] = head
            if samples_lost:
                logger.warning(
                    "Ring buffer consumer %s fell behind by %d samples (dropped from ring)",
                    consumer_id, samples_lost,
                )
            return np.concatenate(collected, axis=0) if collected else np.empty((0, 0), dtype=float)

    def reset_ring_cursor(self, consumer_id: str) -> None:
        """Drop the cursor for ``consumer_id``. Next read starts at head."""
        with self._ring_lock:
            self._ring_cursors.pop(consumer_id, None)

    def _ring_buffered_samples_locked(self) -> int:
        """Sum of rows currently in the ring deque. Caller holds ``_ring_lock``."""
        return sum(len(chunk) for chunk in self._ring_data)

    def stop(self) -> None:
        """Abort any running scans and clean up workers.

        AO is stopped **before** AI so the heater drops to the rest voltage
        (and the chip stops being driven) before we lose the ability to
        observe what is happening on AI.
        """
        # Drop heater first.
        if self._ao_handler is not None:
            self._ao_handler.stop()
        # Then tear down AI workers (ring buffer worker reads from AI, so
        # stopping AI before joining it is fine -- the worker just sees
        # ScanStatus != RUNNING and exits cleanly).
        self.stop_ring_buffer()
        if self._ai_handler is not None:
            self._ai_handler.stop()

    def stop_ao(self) -> None:
        """Stop AO output only; AI keeps running.

        Useful when the GUI wants to halt a CONTINUOUS modulation drive
        (``ao_modulated``) without tearing down the persistent AI scan
        held by the AIProvider.
        """
        if self._ao_handler is not None:
            self._ao_handler.stop()

    def zero_ao(self) -> None:
        """Drive every configured AO channel to 0 V (best-effort safety net).

        Called on disconnect / abort so the heater is not left latched at its
        last commanded value. A bare ``stop_ao`` only halts the scan; the MCC
        DAC then holds its last sample until reset, which on a real chip means
        the heater stays powered after the operator pressed Off / disconnected.
        ``set_voltage`` stops any running scan first, so this also tears down a
        CONTINUOUS modulation drive. Errors are swallowed -- this runs on the
        teardown path and must not mask the original shutdown.
        """
        try:
            for ch in range(
                self._ao_params.low_channel, self._ao_params.high_channel + 1
            ):
                self.ao_set(ch, 0.0)
        except Exception:
            logger.exception("Failed to drive AO to 0 V on shutdown")

    # ------------------------------------------------------------------
    # Internal: finite AI collection (no point loss)
    # ------------------------------------------------------------------
    def _collect_finite_ai(
        self,
        ai_handler: AiDeviceHandler,
        ao_handler: AoDeviceHandler,
        seconds: float,
        ai_channels: Sequence[int],
    ) -> pd.DataFrame:
        n_ai_chans = self._ai_params.channel_count()
        sample_rate = self._ai_params.sample_rate
        samples_per_channel = sample_rate  # 1 s of buffer per channel
        half_per_channel = samples_per_channel // 2
        if half_per_channel <= 0:
            raise ValueError("AI sample_rate must be at least 2")
        # The half-buffer flip protocol reshapes both halves to
        # ``(half_per_channel, n_chans)``. The upper half slice has
        # ``samples_per_channel - half_per_channel`` rows, which equals
        # ``half_per_channel`` only when ``samples_per_channel`` is even.
        # Reject odd rates loudly instead of crashing in ``np.reshape``.
        if samples_per_channel % 2 != 0:
            raise ValueError(
                f"AI sample_rate must be even (got {sample_rate}); the "
                "half-buffer flip protocol requires an even buffer length."
            )
        total_samples_per_channel = int(round(sample_rate * seconds))

        buf = ai_handler.get_buffer()
        # Derive ``half_buf_len`` from the channel-aligned half so that the
        # reshape below is always exact. Computing it as ``len(buf) // 2`` is
        # only correct when ``samples_per_channel`` is even AND ``len(buf)``
        # is divisible by ``n_ai_chans`` — both true today (20000 samples /
        # 6 channels) but easily violated with a different sample rate or a
        # different AI channel range.
        half_buf_len = half_per_channel * n_ai_chans

        # Naming convention used below:
        #   "lower half" = ``buf[:half_buf_len]``  (samples 0 .. half-1)
        #   "upper half" = ``buf[half_buf_len:]``  (samples half .. end)
        # We snapshot the lower half once ``current_index`` has moved into the
        # upper half (the lower half is full and stable) and snapshot the upper
        # half once ``current_index`` has wrapped back into the lower half.
        chunks: List[np.ndarray] = []
        last_index = 0
        lower_half_collected = False
        upper_half_collected = False
        deadline = time.monotonic() + seconds + 5.0  # generous safety margin

        collected = 0
        while collected < total_samples_per_channel:
            if self._cancel.is_set():
                logger.info("AI collection cancelled by request_stop")
                break
            if time.monotonic() > deadline:
                logger.warning("AI collection deadline exceeded")
                break
            ai_status, transfer = ai_handler.status()
            if ai_status != ul.ScanStatus.RUNNING:
                # Driver stopped (probably an underrun). Drain & exit.
                break
            current_index = transfer.current_index

            # writer just crossed half-buffer boundary upwards:
            # lower half is now complete and safe to copy.
            if (
                not lower_half_collected
                and current_index >= half_buf_len
                and last_index < half_buf_len
            ):
                chunks.append(
                    np.asarray(buf[:half_buf_len], dtype=float)
                    .reshape(half_per_channel, n_ai_chans)
                    .copy()
                )
                collected += half_per_channel
                lower_half_collected = True
                upper_half_collected = False

            # writer just wrapped from the upper half back to the lower:
            # upper half is now complete and safe to copy.
            elif (
                not upper_half_collected
                and current_index < last_index
                and last_index >= half_buf_len
            ):
                chunks.append(
                    np.asarray(buf[half_buf_len:], dtype=float)
                    .reshape(half_per_channel, n_ai_chans)
                    .copy()
                )
                collected += half_per_channel
                upper_half_collected = True
                lower_half_collected = False

            last_index = current_index
            time.sleep(0.001)

        # Observability (todo P0-5 / P1-17): on real hardware a pacer underrun
        # or a missed half-buffer flip shows up as a frame shorter than the
        # commanded length. Surface the count explicitly so a short frame is a
        # visible WARNING, not a silent truncation downstream.
        if collected < total_samples_per_channel:
            logger.warning(
                "AI finite scan short: collected %d / %d samples per channel",
                collected, total_samples_per_channel,
            )
        else:
            logger.info(
                "AI finite scan complete: %d / %d samples per channel",
                collected, total_samples_per_channel,
            )

        if not chunks:
            return pd.DataFrame(columns=list(ai_channels))

        full = np.concatenate(chunks, axis=0)
        full = full[:total_samples_per_channel]

        # Build a DataFrame with the AI channel numbers as columns, then drop
        # the channels the caller does not care about.
        all_channels = list(
            range(self._ai_params.low_channel, self._ai_params.high_channel + 1)
        )
        df = pd.DataFrame(full, columns=all_channels)
        return df.loc[:, list(ai_channels)]

    def _collect_finite_ai_single_shot(
        self,
        ai_handler: AiDeviceHandler,
        total_samples_per_channel: int,
        ai_channels: Sequence[int],
        seconds: float,
    ) -> pd.DataFrame:
        """Collect a single-shot ``DEFAULTIO`` scan (fast-heat).

        The host buffer is the full scan length, so the DAQ DMAs everything and
        we read it once after the scan reaches IDLE -- the host never has to
        keep up mid-scan, which removes the FIFO-OVERRUN failure mode of the
        CONTINUOUS half-flip path (todo P1-30). We only poll the scan status;
        we do not read or copy the buffer until the scan is done.
        """
        n_ai_chans = self._ai_params.channel_count()
        deadline = time.monotonic() + seconds + 5.0  # generous safety margin
        completed = False
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                logger.info("AI single-shot scan cancelled by request_stop")
                break
            ai_status, _ = ai_handler.status()
            if ai_status != ul.ScanStatus.RUNNING:
                completed = True
                break
            time.sleep(0.002)

        if completed:
            logger.info(
                "AI single-shot scan complete: %d samples per channel",
                total_samples_per_channel,
            )
        else:
            logger.warning(
                "AI single-shot scan did not reach IDLE before the deadline; "
                "buffer may be partially filled (%d samples per channel expected)",
                total_samples_per_channel,
            )

        expected = total_samples_per_channel * n_ai_chans
        buf = np.asarray(ai_handler.get_buffer(), dtype=float)[:expected]
        # Reshape to (samples, channels); a short buffer (deadline hit) is
        # trimmed to whole rows so the DataFrame stays rectangular.
        rows = buf.size // n_ai_chans
        full = buf[: rows * n_ai_chans].reshape(rows, n_ai_chans)

        all_channels = list(
            range(self._ai_params.low_channel, self._ai_params.high_channel + 1)
        )
        df = pd.DataFrame(full, columns=all_channels)
        return df.loc[:, list(ai_channels)]

    # ------------------------------------------------------------------
    # Internal: ring-buffer worker
    # ------------------------------------------------------------------
    def _ring_loop(self, ai_handler: AiDeviceHandler, ai_channels: List[int]) -> None:
        n_ai_chans = self._ai_params.channel_count()
        samples_per_channel = ai_handler.samples_per_channel
        half_per_channel = samples_per_channel // 2
        # ``max_chunks`` is the depth of history kept in memory: each chunk
        # holds half of the AI buffer (= 0.5 s of samples), so the ring keeps
        # roughly ``ring_max_seconds`` of data.
        max_chunks = max(1, int(self._ring_max_seconds * 2))

        all_channels = list(
            range(self._ai_params.low_channel, self._ai_params.high_channel + 1)
        )
        keep_indices = [all_channels.index(ch) for ch in ai_channels]

        buf = ai_handler.get_buffer()
        # Channel-aligned half (see _collect_finite_ai for the same reasoning).
        half_buf_len = half_per_channel * n_ai_chans

        last_index = 0
        lower_half_collected = False
        upper_half_collected = False
        appended = 0  # half-buffer chunks copied during this ring session
        driver_stopped = False

        while not self._ring_stop.is_set():
            ai_status, transfer = ai_handler.status()
            if ai_status != ul.ScanStatus.RUNNING:
                driver_stopped = True
                break
            current_index = transfer.current_index

            chunk: Optional[np.ndarray] = None
            if (
                not lower_half_collected
                and current_index >= half_buf_len
                and last_index < half_buf_len
            ):
                chunk = (
                    np.asarray(buf[:half_buf_len], dtype=float)
                    .reshape(half_per_channel, n_ai_chans)[:, keep_indices]
                    .copy()
                )
                lower_half_collected = True
                upper_half_collected = False
            elif (
                not upper_half_collected
                and current_index < last_index
                and last_index >= half_buf_len
            ):
                chunk = (
                    np.asarray(buf[half_buf_len:], dtype=float)
                    .reshape(half_per_channel, n_ai_chans)[:, keep_indices]
                    .copy()
                )
                upper_half_collected = True
                lower_half_collected = False

            if chunk is not None:
                appended += int(chunk.shape[0])
                with self._ring_lock:
                    self._ring_data.append(chunk)
                    self._ring_total_samples += int(chunk.shape[0])
                    while len(self._ring_data) > max_chunks:
                        self._ring_data.popleft()

            last_index = current_index
            time.sleep(0.001)

        # Observability: a clean stop exits because ``_ring_stop`` was set; an
        # unexpected exit (driver no longer RUNNING) usually means an underrun.
        # Log the latter at WARNING so a stalled persistent stream is visible.
        if driver_stopped:
            logger.warning(
                "Ring buffer worker exited: AI scan stopped running after "
                "%d samples per channel (possible underrun)", appended,
            )
        else:
            logger.info(
                "Ring buffer worker stopped cleanly after %d samples per channel",
                appended,
            )

    # ------------------------------------------------------------------
    # Helper used by tests / Tango layer
    # ------------------------------------------------------------------
    def get_ai_data_from_disk(self) -> pd.DataFrame:
        return pd.DataFrame(pd.read_hdf(RAW_DATA_FILE_REL_PATH, key="dataset"))
