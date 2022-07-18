from experiment_manager import ExperimentManager
from daq_device import DaqDeviceHandler
from utils import temperature_to_voltage
from settings import SettingsParser
from calibration import Calibration
from profile_data import TempTimeProfile, VoltageProfile

from scipy import interpolate
from typing import Dict
import pandas as pd
import numpy as np
import logging


class FastHeat:
    _ai_data: pd.DataFrame
    _voltage_profiles: Dict[int, VoltageProfile]

    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings_parser: SettingsParser,
                 temp_time_profile: TempTimeProfile,
                 calibration: Calibration):

        self._set_temp_profile_data(temp_time_profile)

        self._settings_parser = settings_parser
        sample_rate = self._settings_parser.get_ao_params().sample_rate
        self._samples_per_channel = int(temp_time_profile.x.last() / 1000. * sample_rate)

        self._calibration = calibration
        self._daq_device_handler = daq_device_handler
        self._ai_channels = [0, 1, 2, 3, 4, 5]  # TODO: get from somewhere

    def _set_temp_profile_data(self, temp_time_profile: TempTimeProfile):
        if not temp_time_profile.is_valid():
            raise ValueError("Invalid time-temperature profile defined.")
        if temp_time_profile.x.last() % 1000. != 0:  # TODO: think about it
            raise ValueError("Input profile time cannot be packed into integer buffers.")
        self._temp_time_profile = temp_time_profile

    def get_ai_data(self) -> pd.DataFrame:
        """Provides explicit access to the already read AI data."""
        return self._ai_data
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_value is not None:
            logging.error("ERROR. Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))
            self._daq_device_handler.quit()  # TODO: check is it needed

    def arm(self) -> Dict[int, VoltageProfile]:
        self._voltage_profiles[0] = self._get_channel0_voltage()
        self._voltage_profiles[1] = self._get_channel1_voltage()
        return self._voltage_profiles  # returns for debug

    def is_armed(self) -> bool:
        status = not not self._voltage_profiles
        for profile in self._voltage_profiles.values():
            status = status and profile.is_valid()
        return status

    def run(self):
        if self.is_armed():
            with ExperimentManager(self._daq_device_handler,
                                   self._voltage_profiles,
                                   self._settings_parser.get_ai_params(),
                                   self._settings_parser.get_ao_params()) as em:
                em.run()
                self._ai_data = em.get_ai_data(self._ai_channels)

            self._apply_calibration()
        else:
            logging.warning("WARNING. Fast heating cannot be started, since it should be armed first.")

    def _get_channel0_voltage(self) -> VoltageProfile:
        return VoltageProfile(0.1 * np.ones(self._samples_per_channel))

    def _get_channel1_voltage(self) -> VoltageProfile:
        time_values = self._temp_time_profile.x.get()
        interpolation = interpolate.interp1d(x=time_values, y=self._temp_time_profile.y.get(),
                                             kind='linear')
        time_program_points = np.linspace(time_values[0], time_values[-1],
                                          self._samples_per_channel)
        temp_program_points = interpolation(time_program_points)
        volt_program_points = temperature_to_voltage(temp_program_points, self._calibration)
        return VoltageProfile(volt_program_points)

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
        # profile = pd.DataFrame(self.voltage_profiles[1])
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
