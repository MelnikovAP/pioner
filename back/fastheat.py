from experiment_manager import ExperimentManager
from daq_device import DaqDeviceHandler
from utils import temperature_to_voltage
from settings import Settings
from calibration import Calibration
from constants import RAW_DATA_FILE_REL_PATH, EXP_DATA_FILE_REL_PATH, SETTINGS_PATH

from scipy import interpolate
from typing import Dict
import pandas as pd
import numpy as np
import h5py
import logging

class FastHeat:
    # receives time_temp_volt_tables as dict :
    # {"ch0": {"time":[list], "temp":list}, 
    # "ch1": {"time":[list], "temp":list},
    # "ch2": {"time":[list], "temp":list}, 
    # "ch3": {"time":[list], "temp":list}, }
    # voltage can be used instead of temperature ("volt" instead of "temp")
    # if "volt" - no calibration applied
    # if "temp" - calibration applied
    # raw_ai_data transfroms to exp_ai_data with respect to calibration
    # raw_ai_data without calibration transformation can be accessed from RAW_DATA_FILE_REL_PATH
    # only data from specified ai_channels will be saved. For normal fast heating it is [0,1,3,4,5]

    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: Settings,
                 time_temp_volt_tables: dict,
                 calibration: Calibration,
                 ai_channels: list[int],
                 FAST_HEAT_CUSTOM_FLAG=False):

        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._time_temp_volt_tables = time_temp_volt_tables
        self._calibration = calibration
        self._ai_channels = ai_channels
        self._FAST_HEAT_CUSTOM_FLAG = FAST_HEAT_CUSTOM_FLAG

        self._voltage_profiles = dict()
        [self._profile_time, self._samples_per_channel] = self._check_time_temp_volt_tables(self._time_temp_volt_tables)


    def arm(self):
        for chan, table in self._time_temp_volt_tables.items():
            key = list(table.keys())
            key.remove('time')
            key = key[0]

            self._voltage_profiles[chan] = self._interpolate_profile(table['time'], table[key])
            if key=='temp':
                self._voltage_profiles[chan] = temperature_to_voltage(self._voltage_profiles[chan], self._calibration)

    def is_armed(self) -> bool:
        return bool(self._voltage_profiles)

    def run(self):
        with ExperimentManager(self._daq_device_handler,
                               self._settings) as em:
            em.ao_scan(self._voltage_profiles)
            em.ai_continuous(self._ai_channels, do_save_data=True)
            self._ai_data = em.get_ai_data()  # TODO: check warning

        if not self._FAST_HEAT_CUSTOM_FLAG:
            self._apply_calibration()
        self._save_data()
        self._add_info_to_file()

    def _check_time_temp_volt_tables(self, time_temp_volt_tables):
        # 1) checks if all the channels profiles have the same duration
        # 2) for each channel checks if time and corresponding temp/volt 
        # profile have the same length
        # 3) checks if specified time profile can be packed into 1 s buffers

        time_lengths = []
        max_len = 0
        for chan, table in time_temp_volt_tables.items():
            key = list(table.keys())
            key.remove('time')
            key = key[0]
            
            if len(table['time']) != len(table[key]):
                error_str = "Different input number of points for time and temperature/voltage at channel " + chan
                logging.error('FAST_HEAT: ', error_str)
                raise ValueError(error_str)
            
            time_lengths.append(table['time'][-1])
            time_lengths = list(set(time_lengths))
        
        if len(time_lengths)>1:
            error_str = "Different duration for channels profiles"
            logging.error('FAST_HEAT: ', error_str)
            raise ValueError(error_str)

        if time_lengths[-1] % 1000. != 0:
            error_str = "Input profile time cannot be packed into integer buffers (1000 ms)."  # TODO: check
            logging.error('FAST_HEAT: ', error_str)
            raise ValueError(error_str)
        else:
            sample_rate = self._settings.ao_params.sample_rate
            samples_per_channel = int(time_lengths[-1] / 1000. * sample_rate)
        # if tests are fine, returns the duration of profile, the same for each channel
        # + amount of samples (buffer length in points) for each profile
        return time_lengths[0], samples_per_channel

    def _interpolate_profile(self, profile_time, profile_temp_or_volt) -> np.array:
        # profile interpolation with respect to time column in table
        interpolation = interpolate.interp1d(x=profile_time, y=profile_temp_or_volt, kind='linear')
        
        time_program_points = np.linspace(profile_time[0], profile_time[-1], self._samples_per_channel)
        temp_or_volt_program_points = interpolation(time_program_points)

        return temp_or_volt_program_points

    def _apply_calibration(self):

        # add timescale in ms
        end_time_ms = 1000*len(self._ai_data)/self._settings.ao_params.sample_rate
        step = 1000/self._settings.ao_params.sample_rate
        self._ai_data['time'] = np.arange(0, end_time_ms, step)

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
        self._ai_data['Uref'] = self._voltage_profiles['ch1']   # Uref equals to the voltage sent on guard heaters
        
        self._ai_data.drop(self._ai_channels, axis=1, inplace=True)

    def _save_data(self):
        fpath = EXP_DATA_FILE_REL_PATH
        with h5py.File(fpath, 'w') as f:
            data = f.create_group('data')
            data.create_dataset('time', data=self._ai_data['time'])
            data.create_dataset('Taux', data=self._ai_data['Taux'])
            data.create_dataset('Thtr', data=self._ai_data['Thtr'])
            data.create_dataset('Uref', data=self._ai_data['Uref'])
            data.create_dataset('temp', data=self._ai_data['temp'])
            data.create_dataset('temp-hr', data=self._ai_data['temp-hr'])

    def _add_info_to_file(self):
        fpath = EXP_DATA_FILE_REL_PATH
        with h5py.File(fpath, 'a') as f:
            f.create_dataset('calibration', data=self._calibration.get_str())
            f.create_dataset('settings', data=self._settings.get_str())

if __name__ == '__main__':
    
    settings = Settings(SETTINGS_PATH)
    time_temp_volt_tables = {'ch0':{'time':[0, 3000], 'volt':[1,1]},
                            'ch1':{'time':[0, 100, 1100, 1900, 2900, 3000], 'temp':[0, 0, 5, 5, 0, 0]},
                            'ch2':{'time':[0, 3000], 'volt':[5,5]},
                            # 'ch3':{'time':[0,2000,2000], 'volt':[0,0,0]}
                            }
    calibration = Calibration()
    ai_channels = [0, 1, 3, 4, 5]

    daq_params = settings.daq_params
    daq_device_handler = DaqDeviceHandler(daq_params)
    daq_device_handler.try_connect()

    fh = FastHeat(daq_device_handler, settings, time_temp_volt_tables, calibration, ai_channels)
    fh.arm()
    fh.run()

    daq_device_handler.disconnect()