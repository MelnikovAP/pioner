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
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from pioner.back.acquisition import AIProvider, create_ai_provider
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.experiment_manager import ExperimentManager
from pioner.back.mock_uldaq import DAQ_AVAILABLE
from pioner.back.modes import apply_calibration, create_mode, save_run_to_h5
from pioner.shared.calibration import Calibration
from pioner.shared.constants import (
    CALIBRATION_FILE_REL_PATH,
    DEFAULT_CALIBRATION_FILE_REL_PATH,
    EXP_DATA_FILE_REL_PATH,
)
from pioner.shared.settings import BackSettings

logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Experiment (mode arm/run)
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def arm(self, mode_name: str, programs_json: str) -> None:
        """Arm ``mode_name`` (``fast`` / ``slow`` / ``iso``) with a JSON payload."""

    @abc.abstractmethod
    def run(self) -> Optional[pd.DataFrame]:
        """Run the armed mode; return the result frame (``None`` if no data)."""

    def stop_run(self) -> None:
        """Abort an in-flight run (only meaningful for iso today)."""

    # -- convenience wrappers mirroring the legacy GUI verbs ----------
    def arm_fast_heat(self, programs_json: str) -> None:
        self.arm("fast", programs_json)

    def run_fast_heat(self) -> Optional[pd.DataFrame]:
        return self.run()

    def arm_iso_mode(self, programs_json: str) -> None:
        self.arm("iso", programs_json)

    def run_iso_mode(self) -> Optional[pd.DataFrame]:
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
    _ISO_CONSUMER = "local_controller_iso_run"

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

    # -- experiment ----------------------------------------------------
    def arm(self, mode_name: str, programs_json: str) -> None:
        if self._daq is None:
            raise RuntimeError("LocalDeviceController is not connected")
        programs = json.loads(programs_json)
        self._mode_name = mode_name.lower().strip()
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

    def run(self) -> Optional[pd.DataFrame]:
        if self._mode is None or not self._mode.is_armed():
            logger.warning("run() called with no armed mode")
            return None
        # Iso streams live (P1-17, Approach C): it drives only AO and reads
        # AI from the persistent ring buffer, so the GUI live plot keeps
        # updating during the run. Fast / slow still own a finite AI scan
        # that collides with the persistent ring, so for those we pause the
        # live stream around the run and resume afterwards. Lifting the
        # pause for fast/slow needs the mode-side AI refactor (P1-17,
        # Approach A) and real-hardware sample-alignment validation.
        if self._mode_name == "iso" and self._provider is not None and self._provider.is_active():
            df = self._run_iso_streaming()
        else:
            self._pause_stream()
            try:
                df = self._mode.run()
            finally:
                self._resume_stream()
        if df is not None and not df.empty:
            try:
                save_run_to_h5(
                    df,
                    self._mode.voltage_profiles,
                    self._last_programs,
                    self._calibration,
                    self._settings,
                    EXP_DATA_FILE_REL_PATH,
                )
            except Exception:
                logger.exception("Failed to persist exp_data.h5")
        return df

    def _run_iso_streaming(self) -> Optional[pd.DataFrame]:
        """Run the armed iso mode against the live persistent ring buffer.

        The mode drives AO on the controller's :class:`ExperimentManager`
        (the one whose ring buffer the live plot reads) and reads AI back
        through the provider's snapshot, never starting a second AI scan.
        The persistent stream stays active for the whole run.

        The persistent ring keeps the full hardware AI range
        (``self._ai_channels``), but the iso mode expects only its own
        curated subset (``mode._ai_channels``, e.g. ch2/guard dropped). The
        snapshot therefore selects the mode's channels, by position, out of
        the ring layout before handing them to the mode.
        """
        if self._em is None or self._provider is None:
            return None
        provider = self._provider  # local binding keeps the non-None narrowing
        mode_channels = list(getattr(self._mode, "_ai_channels", self._ai_channels))
        # Map each mode channel to its column position in the ring layout.
        try:
            keep = [self._ai_channels.index(ch) for ch in mode_channels]
        except ValueError as exc:
            raise RuntimeError(
                f"iso mode AI channels {mode_channels} are not a subset of the "
                f"streamed channels {self._ai_channels}"
            ) from exc

        # Capture only the run window. read_new establishes its cursor at the
        # current head on the first call (returning the existing ring) and
        # thereafter returns only samples appended since. So we prime the
        # cursor *now* (drop the pre-run backlog) and read the delta in the
        # snapshot, giving the samples taken while AO was driving rather than
        # the trailing ring contents (which would include pre-run baseline).
        # reset_ring_cursor first guarantees a clean "first call" even if a
        # previous iso run left a stale cursor. The AO drive starts inside
        # mode.run() a sub-millisecond after priming, so at most a couple of
        # pre-drive samples leak in -- negligible for a stationary iso run.
        self._em.reset_ring_cursor(self._ISO_CONSUMER)
        provider.read_new(self._ISO_CONSUMER)  # prime cursor at head

        def snapshot() -> np.ndarray:
            raw = provider.read_new(self._ISO_CONSUMER)
            if raw.size == 0:
                return raw
            return raw[:, keep]

        return self._mode.run(em=self._em, snapshot=snapshot)

    def stop_run(self) -> None:
        stop = getattr(self._mode, "stop", None) if self._mode is not None else None
        if stop is not None:
            stop()

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

    def run(self) -> Optional[pd.DataFrame]:
        self._device.run()
        return self._download_exp_data()

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
