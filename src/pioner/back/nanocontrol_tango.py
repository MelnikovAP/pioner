"""Tango device server exposing the three calorimetry modes.

The server is intentionally thin: every command unpacks JSON from the wire,
delegates to one of :class:`pioner.back.modes.{FastHeat,SlowMode,IsoMode}`,
and logs the outcome. The mode name is selected by the caller via the
``select_mode`` command (defaults to ``"fast"`` for backwards compatibility).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .mock_uldaq import uldaq as ul

try:  # pragma: no cover - tango may not be present on dev hosts
    from tango.server import Device, attribute, command, pipe
    TANGO_AVAILABLE = True
except ImportError:  # pragma: no cover
    Device = object  # type: ignore[assignment]
    TANGO_AVAILABLE = False

    def command(*args, **kwargs):  # type: ignore[no-redef]
        def deco(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return deco(args[0])
        return deco

    def pipe(*args, **kwargs):  # type: ignore[no-redef]
        def deco(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return deco(args[0])
        return deco

    def attribute(*args, **kwargs):  # type: ignore[no-redef]
        def deco(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return deco(args[0])
        return deco

from pioner.shared.calibration import Calibration
from pioner.shared.constants import (
    CALIBRATION_FILE_REL_PATH,
    DEFAULT_CALIBRATION_FILE_REL_PATH,
    LOGS_FOLDER_REL_PATH,
    NANOCONTROL_LOG_FILE_REL_PATH,
    RAW_DATA_FOLDER_REL_PATH,
    SETTINGS_FILE_REL_PATH,
)
from pioner.shared.settings import BackSettings
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.modes import BaseMode, create_mode

logger = logging.getLogger(__name__)


class NanoControl(Device):  # type: ignore[misc]
    """Single-device Tango server for the PIONER chip calorimeter."""

    _mode: Optional[BaseMode]

    def init_device(self) -> None:  # pragma: no cover - tango entry point
        if TANGO_AVAILABLE:
            super().init_device()
        self._do_initial_setup()

    def _do_initial_setup(self) -> None:
        os.makedirs(LOGS_FOLDER_REL_PATH, exist_ok=True)
        os.makedirs(RAW_DATA_FOLDER_REL_PATH, exist_ok=True)
        logging.basicConfig(
            filename=NANOCONTROL_LOG_FILE_REL_PATH,
            encoding="utf-8",
            level=logging.INFO,
            filemode="w",
            format="%(asctime)s %(message)s",
            datefmt="%m/%d/%Y %H:%M:%S",
        )

        self._calibration = Calibration()
        self.apply_default_calibration()

        self._settings = BackSettings(SETTINGS_FILE_REL_PATH)
        self._daq_device_handler = DaqDeviceHandler(self._settings.daq_params)
        self._mode = None
        self._mode_name = "fast"
        logger.info("Tango server initial setup done")

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @command
    def set_connection(self) -> None:
        try:
            self._daq_device_handler.try_connect()
            logger.info("Connected to DAQ board")
        except ul.ULException as exc:
            logger.error("ULException while connecting: code=%s, %s", exc.error_code, exc.error_message)
            self._daq_device_handler.quit()
        except TimeoutError as exc:
            logger.error("Connection timed out: %s", exc)
            self._daq_device_handler.quit()

    @command
    def disconnect(self) -> None:
        self._daq_device_handler.disconnect()
        logger.info("Disconnected from DAQ board")

    @pipe
    def get_info(self):
        return (
            "Information",
            dict(
                developer="Alexey Melnikov & Evgenii Komov",
                contact="alexey0703@esrf.fr",
                model="pioner 1.0",
                version_number=1.0,
            ),
        )

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------
    @command(dtype_in=str)
    def load_calibration(self, str_calib: str) -> None:
        calib_dir = os.path.dirname(CALIBRATION_FILE_REL_PATH)
        if calib_dir:
            os.makedirs(calib_dir, exist_ok=True)
        with open(CALIBRATION_FILE_REL_PATH, "w", encoding="utf-8") as f:
            json.dump(json.loads(str_calib), f, separators=(",", ": "), indent=4)
        logger.info("Calibration file updated from external string at %s", CALIBRATION_FILE_REL_PATH)

    @command
    def apply_default_calibration(self) -> None:
        try:
            self._calibration.read(DEFAULT_CALIBRATION_FILE_REL_PATH)
            logger.info(
                "Applied default calibration from %s", DEFAULT_CALIBRATION_FILE_REL_PATH
            )
        except Exception as exc:
            logger.error("Error applying default calibration: %s", exc)

    @command
    def apply_calibration(self) -> None:
        try:
            self._calibration.read(CALIBRATION_FILE_REL_PATH)
            logger.info("Applied calibration from %s", CALIBRATION_FILE_REL_PATH)
        except Exception as exc:
            logger.error("Error applying calibration: %s", exc)

    @pipe(label="Current calibration")
    def get_current_calibration(self):
        return "calib", dict(calib=self._calibration.get_str())

    # ------------------------------------------------------------------
    # Settings (sample rate)
    # ------------------------------------------------------------------
    @pipe(label="Current sample rate")
    def get_sample_rate(self):
        return "sr", dict(sr=self._settings.ai_params.sample_rate)

    @command(dtype_in=int)
    def set_sample_scan_rate(self, scan_rate: int) -> None:
        self._settings.ai_params.sample_rate = int(scan_rate)
        self._settings.ao_params.sample_rate = int(scan_rate)
        logger.info("Sample rate set to %d Hz", scan_rate)

    @command
    def reset_sample_scan_rate(self) -> None:
        self._settings.parse_ai_params()
        self._settings.parse_ao_params()

    # ------------------------------------------------------------------
    # Mode selection
    # ------------------------------------------------------------------
    @command(dtype_in=str)
    def select_mode(self, name: str) -> None:
        name = name.lower().strip()
        if name not in ("fast", "slow", "iso"):
            raise ValueError(f"Unknown mode {name!r}; valid: fast/slow/iso")
        self._mode_name = name
        logger.info("Selected mode: %s", name)

    @command(dtype_in=str)
    def arm(self, programs_json: str) -> None:
        """Arm the currently-selected mode with a JSON program payload."""
        programs = json.loads(programs_json)
        self._mode = create_mode(
            self._mode_name,
            self._daq_device_handler,
            self._settings,
            self._calibration,
            programs,
        )
        self._mode.arm()
        logger.info("Mode %s armed", self._mode_name)

    @command
    def run(self) -> None:
        if self._mode is None or not self._mode.is_armed():
            logger.warning("Mode is not armed")
            return
        logger.info("Running mode %s", self._mode_name)
        self._mode.run()
        logger.info("Mode %s finished", self._mode_name)

    @command
    def stop_run(self) -> None:
        """Abort an in-flight ``run()`` (only meaningful for iso, today)."""
        mode = self._mode
        stop = getattr(mode, "stop", None) if mode is not None else None
        if stop is None:
            logger.warning("Active mode does not support stop_run")
            return
        stop()
        logger.info("Mode %s stop requested", self._mode_name)

    # ------------------------------------------------------------------
    # Legacy compatibility (kept so existing GUI calls keep working)
    # ------------------------------------------------------------------
    @command(dtype_in=str)
    def arm_fast_heat(self, programs_json: str) -> None:
        self._mode_name = "fast"
        self.arm(programs_json)

    @command
    def run_fast_heat(self) -> None:
        self.run()

    @command(dtype_in=str)
    def arm_iso_mode(self, programs_json: str) -> None:
        self._mode_name = "iso"
        self.arm(programs_json)

    @command
    def run_iso_mode(self) -> None:
        self.run()


if __name__ == "__main__":  # pragma: no cover - CLI launcher
    if not TANGO_AVAILABLE:
        raise SystemExit("PyTango is required to run the Tango server")
    NanoControl.run_server()
