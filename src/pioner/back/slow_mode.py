"""Slow heating mode (DC ramp + AC modulation) -- thin facade.

The backend used by the GUI / Tango layer instantiates ``SlowMode`` the same
way it instantiates :class:`pioner.back.fastheat.FastHeat`. This module is a
1:1 forward to :class:`pioner.back.modes.SlowMode` and additionally writes
the legacy HDF5 layout under ``EXP_DATA_FILE_REL_PATH`` for the result viewer.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import h5py
import numpy as np

from pioner.shared.calibration import Calibration
from pioner.shared.constants import EXP_DATA_FILE_REL_PATH
from pioner.shared.modulation import ModulationParams
from pioner.shared.settings import BackSettings
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.modes import DEFAULT_AI_CHANNELS, SlowMode as _SlowMode

logger = logging.getLogger(__name__)


class SlowMode:
    def __init__(
        self,
        daq_device_handler: DaqDeviceHandler,
        settings: BackSettings,
        time_temp_volt_tables: Dict[str, dict],
        calibration: Calibration,
        ai_channels: List[int] = list(DEFAULT_AI_CHANNELS),
        modulation: Optional[ModulationParams] = None,
        modulation_channel: str = "ch1",
    ) -> None:
        self._mode = _SlowMode(
            daq_device_handler,
            settings,
            calibration,
            time_temp_volt_tables,
            ai_channels=ai_channels,
            modulation=modulation,
            modulation_channel=modulation_channel,
        )
        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._calibration = calibration
        self._time_temp_volt_tables = time_temp_volt_tables
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

    def _save_data(self) -> None:
        if self._ai_data is None:
            return
        with h5py.File(EXP_DATA_FILE_REL_PATH, "w") as f:
            data = f.create_group("data")
            for col in (
                "time",
                "Taux",
                "Thtr",
                "Uref",
                "temp",
                "temp-hr",
                "temp-hr_amp",
                "temp-hr_phase",
            ):
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


__all__ = ["SlowMode"]
