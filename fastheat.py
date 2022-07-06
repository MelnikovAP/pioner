from experiment_manager import ExperimentManager
from utils import temperature_to_voltage
from settings import SettingsParser
from constants import SETTINGS_PATH
from calibration import Calibration

from scipy import interpolate
import numpy as np

class FastHeat:
    def __init__(self, time_temp_table: dict,
                 calibration: Calibration):

        if len(time_temp_table['time']) != len(time_temp_table['temperature']):
            raise ValueError("Different input number of time and temperature points.")

        self._profile_time = time_temp_table['time']
        self._profile_temp = time_temp_table['temperature']

        self._calibration = calibration

        self._ai_channels = [0, 1, 2, 3, 4, 5]

        self._ao_params = SettingsParser(SETTINGS_PATH).get_ao_params()
        self._samples_per_channel = int(self._profile_time[-1] / 1000. * self._ao_params.sample_rate)
        if self._profile_time[-1] % 1000. != 0:
            raise ValueError("Input profile time cannot be packed into integer buffers.")

        self._voltage_profiles = dict()

    def get_ai_data(self):
        """Provides explicit access to the read ai_data."""
        return self.ai_data
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))

    def arm(self):
        # arm 0.1 to 0 channel (Uref). 0.1 - value of the offset. TODO: change
        self._voltage_profiles['ch0'] = self._get_channel0_voltage()
        # arm voltage profile to ch1
        self._voltage_profiles['ch1'] = self._get_channel1_voltage()
        return self._voltage_profiles

    def run(self, voltage_profiles):
        # voltage data for each used AO channel like {'ch0': [.......], 'ch3': [........]}
        with ExperimentManager() as em:
            em.run()
            em.ao_scan(voltage_profiles)
            em.ai_continuous(SAVE_DATA=True)
            self.ai_data = em.get_ai_data(self._ai_channels)
            
        self._apply_calibration()

    def _get_channel0_voltage(self):
        return np.ones(self._samples_per_channel) / 10.       # apply 0.1 voltage on channel0

    def _get_channel1_voltage(self):
        # construct voltage profile to ch1
        interpolation = interpolate.interp1d(x=self._profile_time, y=self._profile_temp, kind='linear')
        
        time_program_points = np.linspace(self._profile_time[0], self._profile_time[-1], self._samples_per_channel)
        temp_program_points = interpolation(time_program_points)

        volt_program_points = temperature_to_voltage(temp_program_points, self._calibration)
        return volt_program_points

    def _apply_calibration(self):
        # Taux - mean for the whole buffer
        Uaux = self.ai_data[3].mean()
        Taux = 100. * Uaux
        if Taux < -12.:  # correction for AD595 below -12 C
            Taux = 2.6843 + 1.2709*Taux + 0.0042867*Taux*Taux + 3.4944e-05*Taux*Taux*Taux
        self.ai_data['Taux'] = Taux
        
        # Utpl or temp - temperature of the calibrated internal thermopile + Taux
        self.ai_data[4] *= (1000./11.)              # scaling to mV with the respect of amplification factor of 11
        ax = self.ai_data[4] + self._calibration.utpl0
        self.ai_data['temp'] = self._calibration.ttpl0 * ax + self._calibration.ttpl1 * (ax ** 2)
        self.ai_data['temp'] += Taux

        # temp-hr ??? add explanation Umod mV
        
        self.ai_data[1] *= (1000./121.)             # scaling to mV; why 121?? amplifier cascade??
        ax = self.ai_data[1] + self._calibration.utpl0
        self.ai_data['temp-hr'] = self._calibration.ttpl0 * ax + self._calibration.ttpl1 * (ax ** 2)

        # Uref
        # ===================
        # profile = pd.DataFrame(self.voltage_profiles['ch1'])
        # Uref = pd.concat(profile*(int(len(self.ai_data[0])/len(profile))), ignore_index=True) # generating repeated profiles
        # self.ai_data['Uref'] = profile
        
        # Thtr
        self.ai_data[5] *= 1000.                # Uhtr mV 
        Rhtr = self.ai_data[5] * 0.
        Ih = self._calibration.ihtr0 + self.ai_data[0] * self._calibration.ihtr1
        Rhtr.loc[Ih!=0] = (self.ai_data[5] - self.ai_data[0] * 1000. + self._calibration.uhtr0) * self._calibration.uhtr1 / Ih
        # Rhtr.loc[Ih==0] = 0
        Thtr = self._calibration.thtr0 + \
               self._calibration.thtr1 * (Rhtr + self._calibration.thtrcorr) + \
               self._calibration.thtr2 * ((Rhtr + self._calibration.thtrcorr) ** 2)
        self.ai_data['Thtr'] = Thtr
        self.ai_data['Uhtr'] = self.ai_data[5]
        
        self.ai_data.drop(self._ai_channels, axis=1, inplace=True)
