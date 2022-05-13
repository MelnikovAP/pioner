from experiment_manager import ExperimentManager
from calibration import Calibration
from nanocal_utils import temperature_to_voltage
from settings_parser import SettingsParser
from scipy import interpolate
from typing import Dict, List
from enums_utils import PhysQuantity
import numpy as np
import pandas as pd


class FastHeat:
    def __init__(self, time_temp_table: Dict[PhysQuantity, List[int]],
                 calibration: Calibration,
                 settings: SettingsParser):
        self.time_temp_table = time_temp_table
        if len(self.time_temp_table[PhysQuantity.TIME]) != len(self.time_temp_table[PhysQuantity.TEMPERATURE]):
            raise ValueError("Different imput number of time and temperature points.")
        self.calibration = calibration
        self.settings = settings

        self.profile_time = self.time_temp_table[PhysQuantity.TIME]
        self.profile_temp = self.time_temp_table[PhysQuantity.TEMPERATURE]
        # buffer size, sample_rate*{experiment duration in seconds}

        self.ai_channels = [0, 1, 2, 3, 4, 5]  # TODO: check is it ok here
        self.scan_params = self.settings.get_scan_params()
        self.scan_params.buffer_size = int(self.profile_time[-1]/1000 * \
                                            self.settings.get_scan_params().sample_rate)
        self.daq_params = self.settings.get_daq_params()
        self.ai_params = self.settings.get_ai_params()
        self.ao_params = self.settings.get_ao_params()

    def get_ai_data(self):
        """Provides explicit access to the read ai_data."""
        return self.ai_data
    
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))

    def arm(self) -> Dict[str, np.ndarray]:
        self.voltage_profiles = dict()
        # arm 0.1 to 0 channel (Uref). 0.1 - value of the offset. later to be changed
        self.voltage_profiles['ch0'] = self._get_channel0_voltage()
        # arm voltage profile to ch1
        self.voltage_profiles['ch1'] = self._get_channel1_voltage()
        return self.voltage_profiles

    def run(self, voltage_profiles):
        # voltage data for each used ao channel like {'ch0': [.......], 'ch3': [........]}
        with ExperimentManager(voltage_profiles,
                               self.ai_channels,  # channels to read from ai device
                               self.scan_params,
                               self.daq_params,
                               self.ai_params,
                               self.ao_params) as em:
            em.run()

        self.ai_data = em.get_ai_data()
        self._apply_calibration()

    def _get_channel0_voltage(self):
        return np.ones(self.scan_params.buffer_size) / 10.       # apply 0.1 voltage on channel0

    def _get_channel1_voltage(self):
        # construct voltage profile to ch1
        interpolation = interpolate.interp1d(x=self.profile_time, y=self.profile_temp, kind='linear')
        
        time_program_points = np.linspace(self.profile_time[0], self.profile_time[-1], self.scan_params.buffer_size)
        temp_program_points = interpolation(time_program_points)

        volt_program_points = temperature_to_voltage(temp_program_points, self.calibration)
        return volt_program_points

    def _apply_calibration(self):

        # Taux - mean for the whole buffer
        Uaux = self.ai_data[3].mean()
        Taux = 100.*Uaux
        if Taux < -12:                            # corrrection for AD595 below -12C
            Taux = 2.6843 + 1.2709*Taux + 0.0042867*Taux*Taux + 3.4944e-05*Taux*Taux*Taux
        self.ai_data['Taux'] = Taux
        
        # Utpl or temp - temperature of the calibrated internal termopile + Taux
        self.ai_data[4] *= (1000./11.)              # scaling to mV with the respect of amplification factor of 11
        ax = self.ai_data[4] + self.calibration.utpl0
        self.ai_data['temp'] = self.calibration.ttpl0*ax + self.calibration.ttpl1*(ax**2)
        self.ai_data['temp'] += Taux

        # temp-hr ??? add explanation Umod mV
        
        self.ai_data[1] *= (1000./121.)             # scaling to mV; why 121?? amplifier cascade??
        ax = self.ai_data[1] + self.calibration.utpl0
        self.ai_data['temp-hr'] = self.calibration.ttpl0*ax + self.calibration.ttpl1*(ax**2)

        # Uref
        # ===================
        # profile = pd.DataFrame(self.voltage_profiles['ch1'])
        # Uref = pd.concat(profile*(int(len(self.ai_data[0])/len(profile))), ignore_index=True) # generating repeated profiles
        # self.ai_data['Uref'] = profile
        
        # Thtr
        self.ai_data[5] *= 1000.                # Uhtr mV 
        Rhtr = self.ai_data[5] * 0.
        Ih = self.calibration.ihtr0 + self.ai_data[0]*self.calibration.ihtr1
        Rhtr.loc[Ih!=0] = (self.ai_data[5] - self.ai_data[0]*1000. + self.calibration.uhtr0)*self.calibration.uhtr1/Ih
        Rhtr.loc[Ih==0] = 0
        Thtr = self.calibration.thtr0 + \
                self.calibration.thtr1*(Rhtr+self.calibration.thtrcorr) + \
                self.calibration.thtr2*((Rhtr+self.calibration.thtrcorr)**2)
        self.ai_data['Thtr'] = Thtr
        
        self.ai_data.drop(self.ai_channels, axis=1, inplace=True)
        



