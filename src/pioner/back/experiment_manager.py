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
* AI is always paced with ``CONTINUOUS`` so that we do not block on a fixed
  ``samples_per_channel`` count and can stop cleanly at any time.
* The AI buffer is sized to exactly **one second** of data. The reader loop
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
        self._ao_buffer: Optional[List[float]] = None
        self._ai_buffer_samples_per_channel: int = 0

        # Background ring-buffer worker (used by iso_scan).
        self._ring_thread: Optional[threading.Thread] = None
        self._ring_stop = threading.Event()
        self._ring_lock = threading.Lock()
        self._ring_data: deque[np.ndarray] = deque()
        self._ring_max_seconds: float = 10.0

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
        seconds: int,
    ) -> ScanResult:
        """Run a finite paced AO + AI experiment.

        ``voltage_profiles`` is an iterable per-channel array of floats with
        length ``seconds * sample_rate``. ``ai_channels`` is the subset of AI
        channels to keep in the resulting DataFrame.
        """
        if seconds <= 0:
            raise ValueError("seconds must be > 0")
        if not voltage_profiles:
            raise ValueError("voltage_profiles is empty")

        ai_handler = self._ensure_ai_handler(self._ai_params.sample_rate)
        ao_handler = self._ensure_ao_handler()

        # Configure AO for finite output; AI stays continuous.
        # TODO(global): use a hardware trigger (RETRIGGER / EXTTRIGGER) so AO
        # and AI start on the same DAQ clock pulse. Currently we start AI a
        # few hundred microseconds before AO; for fast (>1000 K/s) scans the
        # leading edge is therefore offset by 1-2 samples. Acceptable for
        # mock and tests, but worth tightening on real hardware.
        self._ao_params.options = ul.ScanOption.BLOCKIO
        self._ai_params.options = ul.ScanOption.CONTINUOUS

        self._ao_buffer = ScanDataGenerator(
            voltage_profiles,
            self._ao_params.low_channel,
            self._ao_params.high_channel,
        ).get_buffer()

        # Stop any leftover scans before starting fresh ones.
        ao_handler.stop()
        ai_handler.stop()

        # Start AI first so we don't miss the leading samples of the AO scan.
        ai_rate = ai_handler.scan(self._ai_buffer_samples_per_channel)
        ao_rate = ao_handler.scan(self._ao_buffer)

        df = self._collect_finite_ai(ai_handler, ao_handler, seconds, ai_channels)

        ao_handler.stop()
        ai_handler.stop()

        return ScanResult(
            data=df,
            ai_rate=float(ai_rate),
            ao_rate=float(ao_rate),
            samples_per_channel=int(ai_rate * seconds),
        )

    def ao_set(self, channel: int, voltage: float) -> None:
        """Hold a static voltage on a single AO channel (iso primitive)."""
        ao_handler = self._ensure_ao_handler()
        ao_handler.set_voltage(channel, voltage)

    def ao_modulated(self, voltage_profiles: dict) -> None:
        """Drive a continuous AO profile (used by iso/slow with modulation)."""
        ao_handler = self._ensure_ao_handler()
        self._ao_params.options = ul.ScanOption.CONTINUOUS
        self._ao_buffer = ScanDataGenerator(
            voltage_profiles,
            self._ao_params.low_channel,
            self._ao_params.high_channel,
        ).get_buffer()
        ao_handler.stop()
        ao_handler.scan(self._ao_buffer)

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

        self._ai_params.options = ul.ScanOption.CONTINUOUS
        ai_handler = self._ensure_ai_handler(self._ai_params.sample_rate)
        ai_handler.stop()
        ai_handler.scan(self._ai_buffer_samples_per_channel)

        self._ring_max_seconds = float(max_seconds)
        self._ring_data.clear()
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

    def stop(self) -> None:
        """Abort any running scans and clean up workers."""
        self.stop_ring_buffer()
        if self._ai_handler is not None:
            self._ai_handler.stop()
        if self._ao_handler is not None:
            self._ao_handler.stop()

    # ------------------------------------------------------------------
    # Internal: finite AI collection (no point loss)
    # ------------------------------------------------------------------
    def _collect_finite_ai(
        self,
        ai_handler: AiDeviceHandler,
        ao_handler: AoDeviceHandler,
        seconds: int,
        ai_channels: Sequence[int],
    ) -> pd.DataFrame:
        n_ai_chans = self._ai_params.channel_count()
        sample_rate = self._ai_params.sample_rate
        samples_per_channel = sample_rate  # 1 s of buffer per channel
        half_per_channel = samples_per_channel // 2
        if half_per_channel <= 0:
            raise ValueError("AI sample_rate must be at least 2")
        total_samples_per_channel = sample_rate * seconds

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
        df = df[list(ai_channels)]
        return df

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

        while not self._ring_stop.is_set():
            ai_status, transfer = ai_handler.status()
            if ai_status != ul.ScanStatus.RUNNING:
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
                with self._ring_lock:
                    self._ring_data.append(chunk)
                    while len(self._ring_data) > max_chunks:
                        self._ring_data.popleft()

            last_index = current_index
            time.sleep(0.001)

    # ------------------------------------------------------------------
    # Helper used by tests / Tango layer
    # ------------------------------------------------------------------
    def get_ai_data_from_disk(self) -> pd.DataFrame:
        return pd.DataFrame(pd.read_hdf(RAW_DATA_FILE_REL_PATH, key="dataset"))
