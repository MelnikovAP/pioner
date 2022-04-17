import numpy

from experiment_manager import ExperimentManager
from calibration import Calibration
from nanocal_utils import temperature_to_voltage
from settings_parser import SettingsParser
from scipy import interpolate
from typing import Dict, List
from enums_utils import PhysQuantity
import numpy as np


class FastHeat:
    def __init__(self, time_temp_table: Dict[PhysQuantity, List[int]],
                 calibration: Calibration,
                 settings: SettingsParser):
        self.time_temp_table = time_temp_table
        if len(self.time_temp_table[PhysQuantity.TIME]) != len(self.time_temp_table[PhysQuantity.TEMPERATURE]):
            raise ValueError("Different imput number of time and temperature points.")

        self.calibration = calibration
        self.settings = settings

        self.ai_channels = [0, 1, 2, 3, 4, 5]  # TODO: check is it ok here

    def get_ai_data(self):
        """Provides explicit access to the read ai_data."""
        return self.ai_data
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))

    def arm(self) -> Dict[str, numpy.ndarray]:
        voltage_profiles = dict()
        # arm 0.1 to 0 channel (Uref). 0.1 - value of the offset. later to be changed
        voltage_profiles['ch0'] = self._get_channel0_voltage()
        # arm voltage profile to ch1
        voltage_profiles['ch1'] = self._get_channel1_voltage()
    
        return voltage_profiles

    def run(self, voltage_profiles):
        # voltage data for each used ao channel like {'ch0': [.......], 'ch3': [........]}
        with ExperimentManager(voltage_profiles,
                               self.ai_channels,  # channels to read from ai device
                               self.settings.get_scan_params(),
                               self.settings.get_daq_params(),
                               self.settings.get_ai_params(),
                               self.settings.get_ao_params()) as em:
            em.run()
        self.ai_data = em.get_ai_data()

        self._apply_calibration()

    def _get_channel0_voltage(self):
        return np.ones(self.time_temp_table[PhysQuantity.TIME][-1]) / 10.

    def _get_channel1_voltage(self):
        # construct voltage profile to ch1
        time = self.time_temp_table[PhysQuantity.TIME]
        temp = self.time_temp_table[PhysQuantity.TEMPERATURE]
        interpolation = interpolate.interp1d(x=time, y=temp, kind='linear')

        points_num = time[-1] + 1  # to get "time[-1]" intervals !!
        time = np.linspace(time[0], time[-1], points_num)
        temp = interpolation(time)

        return temperature_to_voltage(temp, self.calibration)

    def _apply_calibration(self):
        pass
