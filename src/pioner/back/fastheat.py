"""Backwards-compatible shim around :class:`pioner.back.modes.FastHeat`.

Existing call sites (Tango server, scripts in ``docs/``) instantiated
``FastHeat`` directly with positional arguments and a ``FAST_HEAT_CUSTOM_FLAG``
boolean. This module forwards those calls to the unified mode hierarchy in
:mod:`pioner.back.modes` and writes the legacy ``exp_data.h5`` file when
``run()`` is called.
"""

from __future__ import annotations

import logging
from typing import Dict, List

import h5py
import numpy as np

from pioner.shared.calibration import Calibration
from pioner.shared.channels import DEFAULT_AI_CHANNELS
from pioner.shared.constants import EXP_DATA_FILE_REL_PATH
from pioner.shared.settings import BackSettings
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.modes import FastHeat as _FastHeatMode

logger = logging.getLogger(__name__)


class FastHeat:
    """Legacy facade for the fast heating mode.

    Parameters
    ----------
    daq_device_handler:
        An already-connected :class:`DaqDeviceHandler`.
    settings:
        Parsed :class:`BackSettings`.
    time_temp_volt_tables:
        ``{"chN": {"time": [...], "temp": [...]}}`` (or ``"volt"``).
    calibration:
        Active calibration.
    ai_channels:
        Subset of AI channels to keep in the output. Defaults to the canonical
        ``[0, 1, 3, 4, 5]`` used by the rest of the code base.
    FAST_HEAT_CUSTOM_FLAG:
        If ``True``, do not run the calibration step. Kept for the GUI's
        "expert" mode.
    """

    def __init__(
        self,
        daq_device_handler: DaqDeviceHandler,
        settings: BackSettings,
        time_temp_volt_tables: Dict[str, dict],
        calibration: Calibration,
        ai_channels: List[int] = list(DEFAULT_AI_CHANNELS),
        FAST_HEAT_CUSTOM_FLAG: bool = False,
    ) -> None:
        self._mode = _FastHeatMode(
            daq_device_handler,
            settings,
            calibration,
            time_temp_volt_tables,
            ai_channels=ai_channels,
        )
        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._calibration = calibration
        self._time_temp_volt_tables = time_temp_volt_tables
        self._FAST_HEAT_CUSTOM_FLAG = bool(FAST_HEAT_CUSTOM_FLAG)
        self._ai_data = None

    def arm(self) -> None:
        self._mode.arm()

    def is_armed(self) -> bool:
        return self._mode.is_armed()

    def run(self) -> None:
        df = self._mode.run()
        self._ai_data = df
        self._save_data()
        self._add_info_to_file()

    # ------------------------------------------------------------------
    # Disk I/O kept identical to the historical layout
    # ------------------------------------------------------------------
    def _save_data(self) -> None:
        if self._ai_data is None:
            return
        with h5py.File(EXP_DATA_FILE_REL_PATH, "w") as f:
            data = f.create_group("data")
            for col in ("time", "Taux", "Thtr", "Uref", "temp", "temp-hr"):
                if col in self._ai_data:
                    data.create_dataset(col, data=np.asarray(self._ai_data[col]))

    def _add_info_to_file(self) -> None:
        with h5py.File(EXP_DATA_FILE_REL_PATH, "a") as f:
            f.create_dataset("calibration", data=self._calibration.get_str())
            f.create_dataset("settings", data=self._settings.get_str())
            programs = f.create_group("temp_volt_programs")
            for chan, table in self._time_temp_volt_tables.items():
                key = next(k for k in table if k != "time")
                program = programs.create_group(chan)
                program.create_dataset("time", data=np.asarray(table["time"]))
                program.create_dataset(key, data=np.asarray(table[key]))
            profiles = f.create_group("voltage_profiles")
            for chan, profile in self._mode.voltage_profiles.items():
                profiles.create_dataset(chan, data=np.asarray(profile))


__all__ = ["FastHeat"]
