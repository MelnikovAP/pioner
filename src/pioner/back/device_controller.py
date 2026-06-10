"""Device controller abstraction: one surface, two backends.

The GUI (``front/mainWindow.py``) talks to the instrument through a
:class:`DeviceController` instead of a raw Tango ``DeviceProxy``. Two
implementations exist:

* :class:`LocalDeviceController` -- owns a :class:`DaqDeviceHandler`,
  :class:`ExperimentManager`, :class:`AIProvider` and
  :class:`Calibration` directly, in-process. Runs experiments by
  calling :func:`create_mode` and returns the result ``DataFrame``
  straight back. Picks the real ``uldaq`` driver or the pure-Python
  mock automatically (see ``mock_uldaq.DAQ_AVAILABLE``), so it is the
  backend used for both mock development and (eventually) direct
  hardware control without a Tango server.

* :class:`TangoDeviceController` -- thin wrapper around a Tango
  ``DeviceProxy``, preserving the legacy network path. NOTE: this path
  is currently *not actual* (the Tango server is incompatible with the
  persistent AI session, see ``docs/live-streaming.md`` and
  ``nanocontrol_tango.py``). It is kept so the wiring can be repaired
  later (todo P1-17) without re-touching the GUI. Live-streaming
  methods return empty for the Tango backend.

The contract is intentionally narrow -- exactly the operations the GUI
needs -- and uses plain Python return types (``int``, ``dict``,
``DataFrame``) rather than Tango's pipe tuples, so call sites stay
readable.
"""

from __future__ import annotations

import abc
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from pioner.back.acquisition import AIProvider, DiskRecorder, create_ai_provider
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.experiment_manager import ExperimentManager
from pioner.back.mock_uldaq import DAQ_AVAILABLE
from pioner.back.modes import (
    apply_calibration,
    create_mode,
    finalize_raw_to_h5,
    heater_resistance,
    save_run_to_h5,
)
from pioner.shared.calibration import Calibration
from pioner.shared.constants import (
    CALIBRATION_FILE_REL_PATH,
    DEFAULT_CALIBRATION_FILE_REL_PATH,
    EXP_DATA_FILE_REL_PATH,
)
from pioner.shared.settings import BackSettings

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Outcome of ``DeviceController.run()`` -- uniform across modes (P1-17 4c-3).

    The full dataset lives **on disk**, never returned as an in-RAM frame, so a
    multi-hour run cannot exhaust memory. ``cal_path`` is the calibrated (T)
    ``exp_data.h5``; ``raw_path`` is the raw (U) recorder file for the streaming
    modes (``None`` for fast, which is single-shot and not ring-based). Read the
    result for display with :func:`pioner.back.modes.read_calibrated_h5`
    (decimated). ``mark_index`` is the baseline|run boundary row; ``aborted`` is
    True if a Stop interrupted the run (partial data).
    """

    mode: str
    cal_path: str
    rows: int
    raw_path: Optional[str] = None
    mark_index: Optional[int] = None
    aborted: bool = False


class DeviceController(abc.ABC):
    """Operations the GUI needs from the instrument, backend-agnostic."""

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def connect(self) -> None:
        """Open the device and start live AI streaming (if supported)."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Stop streaming and release the device. Safe to call when idle."""

    @abc.abstractmethod
    def is_connected(self) -> bool:
        ...

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def load_calibration(self, str_calib: str) -> None:
        """Persist a calibration JSON string to the calibration file."""

    @abc.abstractmethod
    def apply_calibration(self) -> None:
        """Load coefficients from the calibration file into the device."""

    @abc.abstractmethod
    def apply_default_calibration(self) -> None:
        """Load the bundled default calibration into the device."""

    @abc.abstractmethod
    def get_calibration(self) -> dict:
        """Return the active calibration as a plain dict."""

    # ------------------------------------------------------------------
    # Sample rate
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def set_sample_rate(self, rate: int) -> None:
        ...

    @abc.abstractmethod
    def reset_sample_rate(self) -> None:
        ...

    @abc.abstractmethod
    def get_sample_rate(self) -> int:
        ...

    def rate_for_mode(self, mode_name: str) -> int:
        """Configured sample rate for ``mode_name`` (P1-31).

        Base fallback: the single active rate. ``LocalDeviceController``
        overrides this with the per-mode map from settings.
        """
        return self.get_sample_rate()

    def override_mode_rate(self, mode_name: str, rate: int) -> None:
        """Set the session sample rate for ``mode_name`` (the UI 'Apply').

        Base fallback: just set the single active rate (no per-mode map).
        """
        self.set_sample_rate(rate)

    # ------------------------------------------------------------------
    # Experiment (mode arm/run)
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def arm(self, mode_name: str, programs_json: str) -> None:
        """Arm ``mode_name`` (``fast`` / ``slow`` / ``iso``) with a JSON payload."""

    @abc.abstractmethod
    def run(self) -> Optional["RunResult"]:
        """Run the armed mode; return a :class:`RunResult` (paths + summary).

        The data lives on disk, not in the return value (``None`` if no mode is
        armed). Read it for display with ``modes.read_calibrated_h5``.
        """

    def stop_run(self) -> None:
        """Abort an in-flight run (only meaningful for iso today)."""

    def start_iso_hold(self) -> None:
        """Start an eternal iso hold (Set & hold) -- non-blocking.

        Default fallback for backends without a dedicated hold primitive
        (e.g. the legacy Tango path): a single blocking ``run()``.
        """
        self.run()

    @property
    def is_holding(self) -> bool:
        """True while an eternal iso hold is driving AO."""
        return False

    # -- convenience wrappers mirroring the legacy GUI verbs ----------
    def arm_fast_heat(self, programs_json: str) -> None:
        self.arm("fast", programs_json)

    def run_fast_heat(self) -> Optional["RunResult"]:
        return self.run()

    def arm_iso_mode(self, programs_json: str) -> None:
        self.arm("iso", programs_json)

    def run_iso_mode(self) -> Optional["RunResult"]:
        return self.run()

    # ------------------------------------------------------------------
    # Live AI streaming (used by the main window's refresh tick)
    # ------------------------------------------------------------------
    def peek_last(self, samples: int) -> np.ndarray:
        """Most recent ``samples`` rows of AI data; empty if not streaming."""
        return np.empty((0, 0), dtype=float)

    def read_new(self, consumer_id: str) -> np.ndarray:
        """Rows appended since this consumer's last call; empty if not streaming."""
        return np.empty((0, 0), dtype=float)

    def is_streaming(self) -> bool:
        return False

    @property
    def ai_sample_rate(self) -> float:
        """AI sample rate in Hz (0.0 when unknown)."""
        return 0.0

    # ------------------------------------------------------------------
    # Backend identity (real DAQ vs mock) -- consumed by the GUI status
    # readout so the operator can tell a live board from the mock.
    # ------------------------------------------------------------------
    @property
    def is_mock(self) -> bool:
        """True when this backend is the pure-Python mock (no real DAQ)."""
        return False

    @property
    def backend_description(self) -> str:
        """Human-readable backend label for the GUI status line."""
        return type(self).__name__

    # ------------------------------------------------------------------
    # Chip-presence detection (P1-36). Read-only, passive. Default: not
    # supported -> ``None`` / unavailable, so callers never gate on it.
    # ------------------------------------------------------------------
    def chip_present(self) -> Optional[bool]:
        """``True``/``False`` if presence detection is enabled and has data,
        else ``None`` (disabled / unsupported / no stream) -- never gates."""
        return None

    def chip_presence_report(self) -> dict:
        """Bench-comparison report of per-channel metrics + strategy verdicts."""
        return {"available": False, "channel": None, "metrics": {}, "verdicts": {}}

    def rhcorr_report(self, window_seconds: float = 1.0) -> dict:
        """Preview the in-situ heater R-correction auto-zero (P1-33), no write."""
        return {"available": False, "reason": "not supported by this backend"}

    def apply_rhcorr(self, window_seconds: float = 1.0) -> dict:
        """Compute and persist the heater R-correction auto-zero (P1-33)."""
        return {"available": False, "reason": "not supported by this backend"}


class LocalDeviceController(DeviceController):
    """In-process backend: DAQ + ExperimentManager + AIProvider + Calibration.

    Parameters
    ----------
    settings
        Parsed :class:`BackSettings` (DAQ / AI / AO / modulation +
        ``AcquisitionMode``).
    calibration_path
        Calibration file to load on :meth:`apply_calibration`. Defaults
        to the bundled default until the GUI applies a user file.
    ring_max_seconds
        In-RAM AI history depth for live streaming.
    """

    _STREAM_CONSUMER = "local_controller_default"
    # Ring consumer-id for the DiskRecorder that streams a slow / finite-iso run
    # to disk (distinct from the live-plot and any other consumer cursors).
    _STREAM_RECORDER = "local_controller_stream_recorder"

    def __init__(
        self,
        settings: BackSettings,
        calibration_path: Optional[str] = None,
        ring_max_seconds: float = 2.0,
    ) -> None:
        self._settings = settings
        self._calibration_path = calibration_path or DEFAULT_CALIBRATION_FILE_REL_PATH
        self._ring_max_seconds = float(ring_max_seconds)

        self._calibration = Calibration()
        self._daq: Optional[DaqDeviceHandler] = None
        self._em: Optional[ExperimentManager] = None
        self._provider: Optional[AIProvider] = None
        self._mode: Any = None
        self._mode_name: str = ""
        self._last_programs: dict = {}
        self._ai_channels: list[int] = []
        # Active sample rate before fast was armed (fast switches to 20 kHz);
        # the ring is resumed at this rate after a fast run (P1-17 fast bullet).
        self._pre_fast_rate: Optional[int] = None
        # Set by stop_run() while a run is in flight; cleared at run() entry.
        # Marks a RunResult / partial save as aborted (P1-17 step 4c-3).
        self._stop_requested: bool = False
        # True while an eternal iso hold (start_iso_hold) is driving AO.
        self._iso_holding: bool = False

    # -- connection ----------------------------------------------------
    def connect(self) -> None:
        if self.is_connected():
            logger.warning("LocalDeviceController.connect called while connected; ignoring")
            return
        self._daq = DaqDeviceHandler(self._settings.daq_params)
        self._daq.try_connect()
        self._em = ExperimentManager(self._daq, self._settings)
        self._provider = create_ai_provider(
            self._settings.acquisition_mode,
            self._em,
            ring_max_seconds=self._ring_max_seconds,
        )
        self._ai_channels = list(
            range(
                self._settings.ai_params.low_channel,
                self._settings.ai_params.high_channel + 1,
            )
        )
        self._provider.on_connect(self._ai_channels)
        # Default to the bundled calibration so derived live values
        # (R, I, T) are computable immediately after connect.
        self.apply_default_calibration()
        logger.info("LocalDeviceController connected (channels=%s)", self._ai_channels)

    def disconnect(self) -> None:
        # Safety: drive the heater (all AO channels) to 0 V before tearing the
        # device down, so an eternal iso hold (or any latched DC) does not
        # leave the chip powered -- the DAC holds its last sample until reset.
        if self._em is not None:
            try:
                self._em.zero_ao()
            except Exception:
                logger.exception("Failed to zero AO on disconnect")
        if self._provider is not None:
            try:
                self._provider.on_disconnect()
            except Exception:
                logger.exception("Provider disconnect failed")
        if self._em is not None:
            try:
                self._em.stop()
            except Exception:
                logger.exception("ExperimentManager.stop failed")
        if self._daq is not None:
            try:
                self._daq.quit()
            except Exception:
                logger.exception("DAQ quit failed")
        self._provider = None
        self._em = None
        self._daq = None
        self._mode = None
        self._iso_holding = False
        logger.info("LocalDeviceController disconnected")

    def is_connected(self) -> bool:
        return self._daq is not None and self._daq.is_connected()

    # -- calibration ---------------------------------------------------
    def load_calibration(self, str_calib: str) -> None:
        calib_dir = os.path.dirname(CALIBRATION_FILE_REL_PATH)
        if calib_dir:
            os.makedirs(calib_dir, exist_ok=True)
        with open(CALIBRATION_FILE_REL_PATH, "w", encoding="utf-8") as f:
            json.dump(json.loads(str_calib), f, separators=(",", ": "), indent=4)
        self._calibration_path = CALIBRATION_FILE_REL_PATH
        logger.info("Calibration file updated at %s", CALIBRATION_FILE_REL_PATH)

    def apply_calibration(self) -> None:
        self._calibration.read(self._calibration_path)
        logger.info("Applied calibration from %s", self._calibration_path)

    def apply_default_calibration(self) -> None:
        self._calibration.read(DEFAULT_CALIBRATION_FILE_REL_PATH)
        self._calibration_path = DEFAULT_CALIBRATION_FILE_REL_PATH
        logger.info("Applied default calibration")

    def get_calibration(self) -> dict:
        return json.loads(self._calibration.get_str())

    # -- sample rate ---------------------------------------------------
    def _validate_rate(self, rate: int) -> None:
        """Fail loud on a sample rate the pipeline cannot honour (P1-31).

        - positive;
        - even (the persistent ring and the slow/iso CONTINUOUS path both use
          the 1 s half-buffer flip, which needs an even length);
        - above the lock-in Nyquist (``f_mod < rate / 2``) whenever AC
          modulation is configured.
        """
        if rate <= 0:
            raise ValueError(f"sample rate must be positive, got {rate}")
        if rate % 2 != 0:
            raise ValueError(f"sample rate must be even (half-buffer flip), got {rate}")
        f_mod = float(getattr(self._settings.modulation, "frequency", 0.0) or 0.0)
        if f_mod > 0 and rate <= 2 * f_mod:
            raise ValueError(
                f"sample rate {rate} Hz is below the lock-in Nyquist for "
                f"f_mod={f_mod} Hz (need rate > {2 * f_mod})"
            )

    def set_sample_rate(self, rate: int) -> None:
        rate = int(rate)
        self._settings.ai_params.sample_rate = rate
        self._settings.ao_params.sample_rate = rate
        logger.info("Sample rate set to %d Hz", rate)
        # The ring buffer was armed at the previous rate; restart it so the
        # live display's time axis stays consistent with the new rate
        # (otherwise the reported ai_sample_rate and the actual sample
        # cadence diverge and the plot's x-scale silently skews). Only
        # restart for an even rate -- start_ring_buffer rejects odd rates
        # (half-buffer flip needs an even length); an invalid value is left
        # stored and surfaced when an experiment is armed, not by killing
        # the live stream here.
        if rate % 2 == 0 and self._provider is not None and self._provider.is_active():
            self._provider.on_disconnect()
            self._provider.on_connect(self._ai_channels)

    def reset_sample_rate(self) -> None:
        self._settings.parse_ai_params()
        self._settings.parse_ao_params()

    def get_sample_rate(self) -> int:
        return int(self._settings.ai_params.sample_rate)

    def rate_for_mode(self, mode_name: str) -> int:
        """Configured rate for ``mode_name`` from the per-mode map (P1-31).

        Falls back to the ``default`` entry for unknown modes, and to the
        single active rate if the settings predate the per-mode map.
        """
        by_mode = getattr(self._settings, "sample_rate_by_mode", None)
        if not by_mode:
            return self.get_sample_rate()
        key = (mode_name or "").lower().strip()
        return int(by_mode.get(key, by_mode["default"]))

    def override_mode_rate(self, mode_name: str, rate: int) -> None:
        """Session override of a mode's rate (the UI 'Apply' button).

        Records the value in the per-mode map so a later ``arm`` of that mode
        picks it up, then applies it as the active rate immediately.
        """
        rate = int(rate)
        self._validate_rate(rate)
        by_mode = getattr(self._settings, "sample_rate_by_mode", None)
        if by_mode is not None:
            by_mode[(mode_name or "").lower().strip()] = rate
        self.set_sample_rate(rate)

    # -- experiment ----------------------------------------------------
    def arm(self, mode_name: str, programs_json: str) -> None:
        if self._daq is None:
            raise RuntimeError("LocalDeviceController is not connected")
        programs = json.loads(programs_json)
        self._mode_name = mode_name.lower().strip()
        # Apply this mode's configured (or session-overridden) sample rate
        # before building the mode, which reads ai_params.sample_rate (P1-31).
        # AO == AI is kept by set_sample_rate. Only switch when the rate
        # actually changes: set_sample_rate restarts the live ring, which would
        # otherwise briefly empty it and stall the stream (e.g. iso == default).
        desired_rate = self.rate_for_mode(self._mode_name)
        self._validate_rate(desired_rate)
        current_rate = self.get_sample_rate()
        if desired_rate != current_rate:
            # Remember the monitor rate before fast so run() can restore it when
            # the (20 kHz) fast scan finishes -- the ring goes back to its
            # pre-fast cadence rather than staying at 20 kHz.
            if self._mode_name == "fast":
                self._pre_fast_rate = current_rate
            self.set_sample_rate(desired_rate)
        self._mode = create_mode(
            self._mode_name,
            self._daq,
            self._settings,
            self._calibration,
            programs,
        )
        self._mode.arm()
        self._last_programs = programs
        logger.info("Mode %s armed", mode_name)

    def run(self) -> Optional[RunResult]:
        """Run the armed mode and return a :class:`RunResult` (paths, not data).

        The full record is written to disk (``cal_path`` calibrated T, plus
        ``raw_path`` raw U for the streaming modes); nothing is held in RAM as a
        returned frame, so a multi-hour run cannot exhaust memory (P1-17 4c-3).
        Per mode:

        * **slow** -- off-ring streaming: drive only the ramp AO on our manager,
          stream raw AI from the persistent ring to disk (no live-stream pause),
          finalise to the calibrated file.
        * **iso** (finite, duration set) -- same off-ring streaming as slow via
          ``_run_streaming(tile_profile=True)`` (the AO buffer is periodic, so
          it is tiled); no live-stream pause. The eternal hold is the separate
          non-recording ``start_iso_hold()``.
        * **fast** -- own single-shot finite scan; pause the live ring around it
          (bounded, sub-second), save its frame.
        """
        if self._mode is None or not self._mode.is_armed():
            logger.warning("run() called with no armed mode")
            return None
        self._stop_requested = False
        logger.info("Run start: mode=%s", self._mode_name)
        cal_path = EXP_DATA_FILE_REL_PATH

        streaming = self._provider is not None and self._provider.is_active()
        if self._mode_name == "slow" and streaming:
            return self._run_streaming(cal_path, tile_profile=False)
        if self._mode_name == "iso" and streaming:
            # Finite iso experiment: same off-ring streaming as slow, but the AO
            # is a periodic/constant buffer, so tile it (P1-17 step 5). The
            # eternal hold is the separate non-recording start_iso_hold().
            return self._run_streaming(cal_path, tile_profile=True)

        # Fast (or any mode without an active ring): own finite scan, pause the
        # live ring around it and resume afterwards.
        self._pause_stream()
        try:
            df = self._mode.run()
        finally:
            # Fast ran at 20 kHz; restore the pre-fast monitor rate before the
            # ring is brought back up so live monitoring resumes at the rate
            # active before fast was armed (P1-17 fast bullet).
            if self._mode_name == "fast" and self._pre_fast_rate is not None:
                self.set_sample_rate(self._pre_fast_rate)
                self._pre_fast_rate = None
            self._resume_stream()
        return self._save_df_result(self._mode_name, df, cal_path)

    def _save_df_result(
        self, mode: str, df: Optional[pd.DataFrame], cal_path: str
    ) -> RunResult:
        """Persist an in-memory result frame (fast / iso) and wrap it in a RunResult."""
        rows = 0
        if df is not None and not df.empty:
            rows = int(len(df))
            try:
                save_run_to_h5(
                    df, self._mode.voltage_profiles, self._last_programs,
                    self._calibration, self._settings, cal_path,
                )
            except Exception:
                logger.exception("Failed to persist %s", cal_path)
        return RunResult(mode=mode, cal_path=cal_path, rows=rows,
                         aborted=self._stop_requested)

    def _run_streaming(self, cal_path: str, tile_profile: bool) -> RunResult:
        """Off-ring streaming run for slow / finite-iso (P1-17 steps 4c-3, 5).

        Drive the AO program (slow ramp or iso hold) on our manager while a
        DiskRecorder streams raw AI from the persistent ring straight to disk --
        the live stream is never paused and the full record never sits in RAM --
        then finalise to a separate calibrated file. ``tile_profile`` is False
        for the slow ramp (profile spans the run) and True for iso (a short AO
        buffer replayed CONTINUOUS / a DC constant).

        ``run()`` returns paths only (a :class:`RunResult`).
        """
        if self._em is None:
            raise RuntimeError("LocalDeviceController is not connected")
        em = self._em
        raw_path = self._raw_path_for(cal_path)
        recorder = DiskRecorder(em, raw_path, consumer_id=self._STREAM_RECORDER)
        recorder.start()
        try:
            recorder.mark_start()                    # program t=0 boundary
            self._mode.run(em=em, snapshot=None)     # drive AO only
        finally:
            recorder.stop()
            # The mode drives AO on our manager (no finite_scan to self-zero on
            # cancel), so on a Stop drive the heater to 0 explicitly.
            if self._stop_requested:
                em.zero_ao()
        mark = recorder.mark_index or 0
        summary = finalize_raw_to_h5(
            raw_path, cal_path,
            sample_rate=float(self._settings.ai_params.sample_rate),
            calibration=self._calibration,
            settings=self._settings,
            voltage_profiles=self._mode.voltage_profiles,
            programs=self._last_programs,
            ai_channels=self._ai_channels,
            modulation=self._settings.modulation,
            program_offset=mark,
            tile_profile=tile_profile,
        )
        rows = int(summary["rows"]) if summary else 0
        return RunResult(mode=self._mode_name, cal_path=cal_path, raw_path=raw_path,
                         rows=rows, mark_index=mark, aborted=self._stop_requested)

    @staticmethod
    def _raw_path_for(cal_path: str) -> str:
        """Raw (U) sibling path for a calibrated (T) path: ``x.h5`` -> ``x_raw.h5``."""
        base, ext = os.path.splitext(cal_path)
        return f"{base}_raw{ext or '.h5'}"

    def start_iso_hold(self) -> None:
        """Drive the armed iso mode and hold AO until stop_run() (non-blocking).

        Returns immediately while AO keeps driving and the persistent AI stream
        keeps feeding the live plot -- the "eternal iso" path. For a finite,
        auto-stopping iso program, arm() + run() with a duration instead.
        """
        if self._mode is None or not self._mode.is_armed():
            raise RuntimeError("start_iso_hold called with no armed iso mode")
        if self._mode_name != "iso":
            raise RuntimeError("start_iso_hold requires the iso mode")
        if self._em is None:
            raise RuntimeError("LocalDeviceController is not connected")
        self._mode.start_hold(self._em)
        self._iso_holding = True
        logger.info("iso hold started")

    @property
    def is_holding(self) -> bool:
        return self._iso_holding

    def stop_run(self) -> None:
        # An eternal iso hold drives AO on our ExperimentManager directly (no
        # run() in flight), so stop it by halting AO rather than via mode.stop.
        if self._iso_holding and self._em is not None:
            # Drive the heater to 0 V (not just stop the scan, which would
            # latch the last setpoint) so aborting a hold leaves the chip cold.
            self._em.zero_ao()
            self._iso_holding = False
            logger.info("iso hold stopped (AO driven to 0 V)")
            return
        logger.info("Stop requested (mode=%s)", self._mode_name)
        self._stop_requested = True
        stop = getattr(self._mode, "stop", None) if self._mode is not None else None
        if stop is not None:
            stop()
        # Slow streaming drives the ramp AO on our manager (no finite_scan to
        # self-zero on cancel), so zero the heater here too (heater safety).
        # Fast's finite_scan zeroes its own manager on cancel.
        if self._mode_name == "slow" and self._em is not None:
            self._em.zero_ao()

    def _pause_stream(self) -> None:
        if self._provider is not None and self._provider.is_active():
            self._provider.on_disconnect()

    def _resume_stream(self) -> None:
        if self._provider is not None and not self._provider.is_active() and self._ai_channels:
            self._provider.on_connect(self._ai_channels)

    # -- live streaming ------------------------------------------------
    def peek_last(self, samples: int) -> np.ndarray:
        if self._provider is None:
            return np.empty((0, 0), dtype=float)
        return self._provider.peek_last(samples)

    def read_new(self, consumer_id: str) -> np.ndarray:
        if self._provider is None:
            return np.empty((0, 0), dtype=float)
        return self._provider.read_new(consumer_id)

    def is_streaming(self) -> bool:
        return self._provider is not None and self._provider.is_active()

    @property
    def ai_sample_rate(self) -> float:
        return float(self._settings.ai_params.sample_rate)

    @property
    def is_mock(self) -> bool:
        # Single source of truth: the mock layer flips DAQ_AVAILABLE to False
        # whenever the real uldaq import failed (no driver / no board host).
        return not DAQ_AVAILABLE

    @property
    def backend_description(self) -> str:
        return "MOCK DAQ (no hardware)" if self.is_mock else "REAL DAQ (uldaq)"

    # ------------------------------------------------------------------
    # Chip-presence detection (P1-36): read-only inspection of the live AI
    # window (thermopile channels), no AO. Strategy + threshold are config-
    # driven (``ChipPresenceConfig``) and OFF by default until validated on the
    # bench via ``chip_presence_report``.
    # ------------------------------------------------------------------
    def _chip_presence_window(self) -> np.ndarray:
        """~0.2 s of the most recent raw AI samples (empty if not streaming)."""
        n = max(1, int(0.2 * self.ai_sample_rate))
        return self.peek_last(n)

    def chip_present(self) -> Optional[bool]:
        cfg = self._settings.chip_presence
        if not cfg.enabled:
            return None  # detection disabled -> unknown; never gates a launch
        from pioner.back.chip_presence import detect, presence_metrics

        metrics = presence_metrics(self._chip_presence_window(), self._ai_channels)
        if not metrics:
            return None  # no stream yet
        return detect(metrics, cfg).present

    def chip_presence_report(self) -> dict:
        from pioner.back.chip_presence import presence_report

        return presence_report(
            self._chip_presence_window(), self._ai_channels, self._settings.chip_presence
        )

    # ------------------------------------------------------------------
    # In-situ heater R-correction auto-zero (P1-33): trim ``thtrcorr`` so the
    # heater-resistance temperature ``Thtr`` agrees with the thermopile
    # ``Ttpl + Taux`` at the current operating point. PIONER only measures the
    # main-heater resistance (no Rhtrd channel), so only ``thtrcorr`` is
    # auto-zeroed (the differential ``thtrdcorr`` path exists in Calibration but
    # has no measured input here). Requires the heater to be powered (e.g.
    # during an iso hold) so ``Rhtr`` is defined.
    # ------------------------------------------------------------------
    def _rhcorr_operating_point(self, window_seconds: float):
        """Mean proxy resistance and target temperature over a recent AI window.

        Returns ``(r_op, t_target, n_valid)`` or ``None`` if no stream / no
        powered sample. ``r_op`` is the mean ``heater_resistance`` over samples
        where the heater current is non-zero; ``t_target`` is the mean ``temp``
        (``Ttpl + Taux``) over those same samples.
        """
        n = max(1, int(window_seconds * self.ai_sample_rate))
        raw = self.peek_last(n)
        if raw.size == 0:
            return None
        channels = self._ai_channels or list(range(raw.shape[1]))
        raw_df = pd.DataFrame(raw, columns=channels)
        rhtr = heater_resistance(raw_df, self._calibration)
        valid = rhtr.notna().to_numpy()
        n_valid = int(valid.sum())
        if n_valid == 0:
            return None
        cal_df = apply_calibration(
            raw_df, self.ai_sample_rate, self._calibration, {}, ai_channels=channels
        )
        # Target temperature on the same powered samples (Ttpl + Taux).
        temp = cal_df["temp"].to_numpy() if "temp" in cal_df.columns else None
        if temp is None:
            return None
        r_op = float(np.nanmean(rhtr.to_numpy()[valid]))
        t_target = float(np.nanmean(temp[valid]))
        return r_op, t_target, n_valid

    def rhcorr_report(self, window_seconds: float = 1.0) -> dict:
        """Preview the heater R-correction auto-zero without mutating or writing.

        Solves for the new ``thtrcorr`` at the current operating point and
        returns the old/new value, final residual and convergence flags so the
        operator can review before committing via :meth:`apply_rhcorr`.
        """
        op = self._rhcorr_operating_point(window_seconds)
        if op is None:
            return {"available": False,
                    "reason": "heater not powered (Rhtr undefined) -- run an iso hold first"}
        r_op, t_target, n_valid = op
        rep = Calibration.solve_rhcorr(
            self._calibration.thtr0, self._calibration.thtr1, self._calibration.thtr2,
            r_op, t_target, corr_start=self._calibration.thtrcorr,
        )
        rep.update({
            "available": True,
            "r_op": r_op,
            "t_target": t_target,
            "n_valid": n_valid,
            "corr_old": float(self._calibration.thtrcorr),
            "field": "thtrcorr",
            # Destination apply_rhcorr would overwrite (the active working
            # calibration file), surfaced so the confirm dialog can name it.
            "target_path": CALIBRATION_FILE_REL_PATH,
        })
        return rep

    def apply_rhcorr(self, window_seconds: float = 1.0) -> dict:
        """Compute the heater R-correction at the current operating point, store
        it in the active calibration, and persist to the user calibration file.

        Writes to ``CALIBRATION_FILE_REL_PATH`` (never the bundled default), so
        an auto-zero always yields a user calibration snapshot. The active
        calibration is then re-pointed at that file.
        """
        op = self._rhcorr_operating_point(window_seconds)
        if op is None:
            return {"available": False,
                    "reason": "heater not powered (Rhtr undefined) -- run an iso hold first"}
        r_op, t_target, n_valid = op
        rep = self._calibration.compute_rhcorr(r_op, t_target)
        rep.update({"available": True, "r_op": r_op, "t_target": t_target, "n_valid": n_valid})
        calib_dir = os.path.dirname(CALIBRATION_FILE_REL_PATH)
        if calib_dir:
            os.makedirs(calib_dir, exist_ok=True)
        self._calibration.write(CALIBRATION_FILE_REL_PATH)
        self._calibration_path = CALIBRATION_FILE_REL_PATH
        rep["written_to"] = CALIBRATION_FILE_REL_PATH
        logger.info(
            "R-correction auto-zero: thtrcorr %.6g -> %.6g (residual %.4g C, "
            "n_valid=%d) written to %s",
            rep["corr_old"], rep["corr"], rep["residual_c"], n_valid,
            CALIBRATION_FILE_REL_PATH,
        )
        return rep

    def calibrate_window(self, raw: np.ndarray) -> pd.DataFrame:
        """Convert a raw AI window into engineering units for live readout.

        Wraps :func:`apply_calibration` with the active calibration and no
        commanded voltage profiles (live monitoring has none), so heater
        R / Thtr come out NaN whenever the heater current is ~0 -- the
        documented correct behaviour, not a fabricated number.
        """
        if raw.size == 0:
            return pd.DataFrame({})
        raw_df = pd.DataFrame(raw, columns=list(range(raw.shape[1])))
        return apply_calibration(
            raw_df,
            float(self._settings.ai_params.sample_rate),
            self._calibration,
            {},
            ai_channels=self._ai_channels or list(range(raw.shape[1])),
        )


class TangoDeviceController(DeviceController):
    """Legacy network backend over a Tango ``DeviceProxy``.

    Kept for the eventual repair of the Tango path (P1-17). It mirrors
    the command surface the GUI used to call directly. Live-streaming is
    not available over Tango today, so the streaming methods inherit the
    empty defaults from :class:`DeviceController`.

    The result download path fetches the experiment HDF5 over HTTP into
    the standard local file and returns it as a frame -- without the
    legacy interactive "save as" dialog, which belongs in the GUI, not a
    controller.
    """

    def __init__(self, settings: Any) -> None:
        # ``settings`` is the GUI's FrontSettings (device_proxy / http_host).
        self._settings = settings
        self._device: Any = None
        self._http_host: str = getattr(settings, "http_host", "")

    def connect(self) -> None:
        import tango  # imported lazily: not installable on macOS dev boxes

        self._device = tango.DeviceProxy(self._settings.device_proxy)
        self._device.set_timeout_millis(10000000)
        self._device.set_connection()

    def disconnect(self) -> None:
        if self._device is not None:
            self._device.disconnect()
        self._device = None

    def is_connected(self) -> bool:
        return self._device is not None

    def load_calibration(self, str_calib: str) -> None:
        self._device.load_calibration(str_calib)

    def apply_calibration(self) -> None:
        self._device.apply_calibration()

    def apply_default_calibration(self) -> None:
        self._device.apply_default_calibration()

    def get_calibration(self) -> dict:
        calib_str = self._device.get_current_calibration[1][0]["value"]
        return json.loads(calib_str)

    def set_sample_rate(self, rate: int) -> None:
        self._device.set_sample_scan_rate(int(rate))

    def reset_sample_rate(self) -> None:
        self._device.reset_sample_scan_rate()

    def get_sample_rate(self) -> int:
        return int(self._device.get_sample_rate[1][0]["value"])

    def arm(self, mode_name: str, programs_json: str) -> None:
        self._device.select_mode(mode_name.lower().strip())
        self._device.arm(programs_json)

    def run(self) -> Optional[RunResult]:
        self._device.run()
        frame = self._download_exp_data()  # writes EXP_DATA_FILE_REL_PATH
        rows = 0 if frame is None else int(len(frame))
        return RunResult(
            mode=getattr(self, "_mode_name", "") or "tango",
            cal_path=EXP_DATA_FILE_REL_PATH,
            rows=rows,
        )

    def stop_run(self) -> None:
        if self._device is not None:
            self._device.stop_run()

    def _download_exp_data(self) -> Optional[pd.DataFrame]:
        import requests  # lazy: only the Tango path needs HTTP

        url = self._http_host + "data/exp_data.h5"
        response = requests.get(url, verify=False)
        os.makedirs(os.path.dirname(EXP_DATA_FILE_REL_PATH) or ".", exist_ok=True)
        with open(EXP_DATA_FILE_REL_PATH, "wb") as f:
            f.write(response.content)
        try:
            import h5py

            frame = pd.DataFrame({})
            with h5py.File(EXP_DATA_FILE_REL_PATH, "r") as h5:
                data = h5["data"]
                for key in list(data.keys()):  # type: ignore[union-attr]
                    frame[key] = data[key][:]  # type: ignore[index]
            return frame
        except Exception:
            logger.exception("Failed to read downloaded exp_data.h5")
            return None


__all__ = ["DeviceController", "LocalDeviceController", "TangoDeviceController"]
