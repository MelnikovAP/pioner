from experiment_manager import ExperimentManager
from daq_device import DaqDeviceHandler
from utils import temperature_to_voltage
from settings import Settings
from calibration import Calibration
from constants import RAW_DATA_FILE_REL_PATH

from scipy import interpolate
from typing import Dict
import pandas as pd
import numpy as np
import h5py
import logging


class FastHeat:
    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: Settings,
                 time_temp_table: dict,
                 calibration: Calibration):

        self._daq_device_handler = daq_device_handler
        self._settings = settings

        self._set_temp_profile_data(time_temp_table)

        self._calibration = calibration

        self._ai_channels = [0, 1, 2, 3, 4, 5]

        sample_rate = self._settings.ao_params().sample_rate
        self._samples_per_channel = int(self._profile_time[-1] / 1000. * sample_rate)
        if self._profile_time[-1] % 1000. != 0:
            error_str = "Input profile time cannot be packed into integer buffers."  # TODO: check
            logging.error(error_str)
            raise ValueError(error_str)

        self._voltage_profiles = dict()

    def _set_temp_profile_data(self, time_temp_table):
        if len(time_temp_table['time']) != len(time_temp_table['temperature']):
            error_str = "Different input number of time and temperature points."
            logging.error(error_str)
            raise ValueError(error_str)
        self._profile_time = time_temp_table['time']
        self._profile_temp = time_temp_table['temperature']

    def get_ai_data(self) -> pd.DataFrame:
        """Provides explicit access to the already read AI data."""
        return self._ai_data
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_value is not None:
            logging.error("ERROR. Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))
            self._daq_device_handler.quit()  # TODO: check is it needed

    def arm(self) -> Dict[str, np.array]:
        # arm 0.1 to 0 channel (Uref). 0.1 - value of the offset. TODO: change
        self._voltage_profiles['ch0'] = self._get_channel0_voltage()
        # arm voltage profile to ch1
        self._voltage_profiles['ch1'] = self._get_channel1_voltage()
        # arm 4.5 V as trigger signal to ch2
        self._voltage_profiles['ch2'] = self._get_channel2_voltage()

        return self._voltage_profiles  # returns for debug. TODO: remove

    def is_armed(self) -> bool:
        return not not self._voltage_profiles

    def run(self):
        # voltage data for each used AO channel like {'ch0': [.......], 'ch3': [........]}
        with ExperimentManager(self._daq_device_handler,
                               self._voltage_profiles,
                               self._settings) as em:
            em.run()
            self._ai_data = em.get_ai_data(self._ai_channels)  # TODO: check warning
            
        self._apply_calibration()
        self._add_info_to_file()

    def _get_channel0_voltage(self) -> np.array:
        return np.ones(self._samples_per_channel) / 10.  # apply 0.1 voltage on channel 0

    def _get_channel1_voltage(self) -> np.array:
        # construct voltage profile to ch1
        interpolation = interpolate.interp1d(x=self._profile_time, y=self._profile_temp, kind='linear')
        
        time_program_points = np.linspace(self._profile_time[0], self._profile_time[-1], self._samples_per_channel)
        temp_program_points = interpolation(time_program_points)

        volt_program_points = temperature_to_voltage(temp_program_points, self._calibration)
        return volt_program_points

    def _get_channel2_voltage(self) -> np.array:
        return np.ones(self._samples_per_channel) * 4.5  # apply 4.5 voltage on channel 2 as trigger

    def _apply_calibration(self):
        # Taux - mean for the whole buffer
        Uaux = self._ai_data[3].mean()
        Taux = 100. * Uaux
        if Taux < -12.:  # correction for AD595 below -12 C
            Taux = 2.6843 + 1.2709 * Taux + 0.0042867 * Taux * Taux + 3.4944e-05 * Taux * Taux * Taux
        self._ai_data['Taux'] = Taux
        
        # Utpl or temp - temperature of the calibrated internal thermopile + Taux
        self._ai_data[4] *= (1000. / 11.)  # scaling to mV with the respect of amplification factor of 11
        ax = self._ai_data[4] + self._calibration.utpl0
        self._ai_data['temp'] = self._calibration.ttpl0 * ax + self._calibration.ttpl1 * (ax ** 2)
        self._ai_data['temp'] += Taux

        # temp-hr ??? add explanation Umod mV
        
        self._ai_data[1] *= (1000. / 121.)  # scaling to mV; why 121?? amplifier cascade??
        ax = self._ai_data[1] + self._calibration.utpl0
        self._ai_data['temp-hr'] = self._calibration.ttpl0 * ax + self._calibration.ttpl1 * (ax ** 2)

        # Uref
        # ===================
        # profile = pd.DataFrame(self.voltage_profiles['ch1'])
        # Uref = pd.concat(profile*(int(len(self.ai_data[0])/len(profile))), ignore_index=True) # generating repeated profiles
        # self.ai_data['Uref'] = profile
        
        # Thtr
        self._ai_data[5] *= 1000.  # Uhtr mV
        Rhtr = self._ai_data[5] * 0.
        Ih = self._calibration.ihtr0 + self._ai_data[0] * self._calibration.ihtr1
        Rhtr.loc[Ih!=0] = (self._ai_data[5] - self._ai_data[0] * 1000. + self._calibration.uhtr0) * self._calibration.uhtr1 / Ih
        # Rhtr.loc[Ih==0] = 0
        Thtr = self._calibration.thtr0 + \
               self._calibration.thtr1 * (Rhtr + self._calibration.thtrcorr) + \
               self._calibration.thtr2 * ((Rhtr + self._calibration.thtrcorr) ** 2)
        self._ai_data['Thtr'] = Thtr
        self._ai_data['Uhtr'] = self._ai_data[5]
        
        self._ai_data.drop(self._ai_channels, axis=1, inplace=True)

    def _add_info_to_file(self):
        fpath = RAW_DATA_FILE_REL_PATH
        logging.info(fpath)
        with h5py.File(fpath, 'a') as f:
            f.create_dataset('calibration', data=self._calibration.get_str())
            f.create_dataset('settings', data=self._settings.get_str())

