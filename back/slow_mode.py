from utils.constants import EXP_DATA_FILE_REL_PATH
from temp_volt_converters import temperature_to_voltage
from experiment_manager import ExperimentManager
from daq_device import DaqDeviceHandler
from calibration import Calibration
from settings import Settings
from utils import square_poly, cubic_poly

from scipy import interpolate
from typing import List
import numpy as np
import h5py
import logging


class SlowMode:
    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: Settings,
                 calibration: Calibration,
                 time_temp_volt_tables: dict,
                 ai_channels: List[int]):

        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._calibration = calibration
        self._time_temp_volt_tables = time_temp_volt_tables
        self._ai_channels = ai_channels

        self._voltage_profiles = dict()
        self._profile_time, self._samples_per_channel = self._check_time_temp_volt_tables(self._time_temp_volt_tables)

    def arm(self):
        for chan, table in self._time_temp_volt_tables.items():
            key = list(table.keys())
            key.remove('time')
            key = key[0]

            self._voltage_profiles[chan] = self._interpolate_profile(table['time'], table[key])
            if key == 'temp':
                self._voltage_profiles[chan] = temperature_to_voltage(self._voltage_profiles[chan], self._calibration)

    def is_armed(self) -> bool:
        return bool(self._voltage_profiles)

    def run(self):
        with ExperimentManager(self._daq_device_handler, self._settings) as em:
            em.ao_scan(self._voltage_profiles)
            em.ai_continuous(self._ai_channels, do_save_data=True)
            self._ai_data = em.get_ai_data()

        self._apply_calibration()
        self._save_data()
        self._add_info_to_file()

    def _check_time_temp_volt_tables(self, time_temp_volt_tables):
        # 1) checks if all the channels profiles have the same duration
        # 2) for each channel checks if time and corresponding temp/volt
        # profile have the same length
        # 3) checks if specified time profile can be packed into 1 s buffers

        time_lengths = []
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

        if len(time_lengths) > 1:
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

    def _interpolate_profile(self, profile_time, profile_temp_or_volt) -> np.ndarray:
        # profile interpolation with respect to time column in table
        interpolation = interpolate.interp1d(x=profile_time, y=profile_temp_or_volt, kind='linear')

        time_program_points = np.linspace(profile_time[0], profile_time[-1], self._samples_per_channel)
        temp_or_volt_program_points = interpolation(time_program_points)

        return temp_or_volt_program_points

    def _apply_calibration(self):
        # Taux - mean for the whole buffer
        Uaux = self._ai_data[3].mean()
        Taux = 100. * Uaux
        if Taux < -12.:  # correction for AD595 below -12 C
            Taux = cubic_poly(Taux, 2.6843, 1.2709, 0.0042867, 3.4944e-05)
        self._ai_data['Taux'] = Taux

        # Utpl or temp - temperature of the calibrated internal thermopile + Taux
        self._ai_data[4] *= (1000. / 11.)  # scaling to mV with the respect of amplification factor of 11
        ax = self._ai_data[4] + self._calibration.utpl0
        self._ai_data['temp'] = square_poly(ax, 0., self._calibration.ttpl0, self._calibration.ttpl1)
        self._ai_data['temp'] += Taux

        # temp-hr ??? add explanation Umod mV

        self._ai_data[1] *= (1000. / 121.)  # scaling to mV; why 121?? amplifier cascade??
        ax = self._ai_data[1] + self._calibration.utpl0
        self._ai_data['temp-hr'] = square_poly(ax, 0., self._calibration.ttpl0, self._calibration.ttpl1)

        # Uref
        # ===================
        # profile = pd.DataFrame(self.voltage_profiles['ch1'])
        # generating repeated profiles
        # Uref = pd.concat(profile*(int(len(self.ai_data[0])/len(profile))), ignore_index=True)
        # self.ai_data['Uref'] = profile

        # Thtr
        self._ai_data[5] *= 1000.  # Uhtr mV
        Rhtr = self._ai_data[5] * 0.
        Ih = self._calibration.ihtr0 + self._ai_data[0] * self._calibration.ihtr1
        Rhtr.loc[Ih != 0] = (self._ai_data[5] - self._ai_data[0] * 1000. + self._calibration.uhtr0) * \
                            self._calibration.uhtr1 / Ih
        # Rhtr.loc[Ih==0] = 0
        Thtr = square_poly((Rhtr + self._calibration.thtrcorr), self._calibration.thtr0,
                           self._calibration.thtr1, self._calibration.thtr2)
        self._ai_data['Thtr'] = Thtr
        self._ai_data['Uhtr'] = self._ai_data[5]

        self._ai_data.drop(self._ai_channels, axis=1, inplace=True)

    def _save_data(self):
        fpath = EXP_DATA_FILE_REL_PATH
        with h5py.File(fpath, 'w') as f:
            data = f.create_group('data')
            data.create_dataset('Taux', data=self._ai_data['Taux'])
            data.create_dataset('Thtr', data=self._ai_data['Thtr'])
            data.create_dataset('Uhtr', data=self._ai_data['Uhtr'])
            data.create_dataset('temp', data=self._ai_data['temp'])
            data.create_dataset('temp-hr', data=self._ai_data['temp-hr'])

    def _add_info_to_file(self):
        fpath = EXP_DATA_FILE_REL_PATH
        with h5py.File(fpath, 'a') as f:
            f.create_dataset('calibration', data=self._calibration.get_str())
            f.create_dataset('settings', data=self._settings.get_str())
