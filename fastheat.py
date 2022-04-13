from ao_data_generator import AoDataGenerator
from experiment_manager import ExperimentManager
from calibration import Calibration
from utils import temperature_to_voltage
from settings_parser import SettingsParser
from scipy import interpolate
import numpy as np
import pandas as pd


class FastHeat:
    def __init__(self, time_temp_table,
                        calibration: Calibration,
                        settings: SettingsParser):
        self.time_temp_table = time_temp_table
        self.calibration = calibration
        self.settings = settings


    def get_ai_data(self):
        """Provides explicit access to the read ai_data."""
        return self.ai_data
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))

    def arm(self):

        self.ai_channels = [0,1,2,3,4,5]
        voltage_profiles = {}
        # arm 0.1 to 0 channel (Uref). 0.1 - value of the offset. later to be changed
        voltage_profiles['ch0'] = np.ones(self.time_temp_table['time'][-1])/10
        # construct voltage profile to ch1
        time = self.time_temp_table['time']
        temp = self.time_temp_table['temp']
        interpolation = interpolate.interp1d(x=time, y=temp, kind = 'linear')
        time = np.linspace(time[0], time[-1], time[-1])
        temp = interpolation(time)
        volt = temperature_to_voltage(temp, self.calibration)
        # arm voltage profile to ch1
        voltage_profiles['ch1'] = volt
    
        return(voltage_profiles)

    def run(self, voltage_profiles):
        with ExperimentManager(voltage_profiles, # voltage data for each used ao channel like {'ch0': [.......], 'ch3': [........]}
                            self.ai_channels, # channels to read from ai device
                            self.settings.get_scan_params(),
                            self.settings.get_daq_params(),
                            self.settings.get_ai_params(),
                            self.settings.get_ao_params()) as em:
            em.run()
        self.ai_data = em.get_ai_data()

        self._apply_calibration()

    def _apply_calibration(self):
        pass
