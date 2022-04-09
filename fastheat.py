from ao_data_generator import AoDataGenerator
from experiment_manager import ExperimentManager
from calibration import Calibration
from utils import voltage_to_temp, temp_to_voltage
from settings_parser import SettingsParser
from scipy import interpolate
from numpy import linspace
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
        # apply 0.1 to 0 channel (Uref). 0.1 - value of the offset. later to be changed
        voltage_profiles['ch0'] = linspace(0.1, 0.1, self.time_temp_table['time'][-1]) 
        # apply voltage profile to ch1
        time = self.time_temp_table['time']
        temp = self.time_temp_table['temp']

        #seslf.volt_temp_matrix = pd.DataFrame()
        #import time as ttt
        #t0 = ttt.time()
        #self.volt_temp_matrix['Volt'] = linspace(0., self.calibration.safevoltage, time[-1])
        #self.volt_temp_matrix['Temp'] = list(map(voltage_to_temp, self.volt_temp_matrix['Volt'], \
        #                                    time[-1]*[self.calibration]))
        #t1 = ttt.time()
        #print('making matrix took', t1-t0, 's')
        #print(self.volt_temp_matrix['Temp'][50:100])

        #import matplotlib.pyplot as plt
        #fig, ax = plt.subplots()
        #ax.plot(self.volt_temp_matrix['Volt'], self.volt_temp_matrix['Temp'])
        #plt.show()

        interpolation = interpolate.interp1d(x=time, y=temp, kind = 'linear')
        time = linspace(time[0], time[-1], time[-1])
        temp = interpolation(time)
        print(temp[100:115])
        import time as ttt
        t0 = ttt.time()
        #volt = list(map(temp_to_voltage, temp, len(temp)*[self.calibration]))
        t1 = ttt.time()
        print('linearisation process took', t1-t0, 's')
        #voltage_profiles['ch1'] = volt
    
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
