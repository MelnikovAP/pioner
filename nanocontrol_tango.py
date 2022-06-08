from tango.server import Device, attribute, pipe, command

import os

from constants import RAW_DATA_PATH, CALIBRATION_PATH, DEFAULT_CALIBRATION_PATH
from calibration import Calibration
from fastheat import FastHeat

import time

class NanoControl(Device):

    def init_device(self):
        Device.init_device(self)
        self.calibration = Calibration()
        self.time_temp_table = {'time':[], 
                                'temperature':[]
                                }
    
    def change_calibration(self, path):
        self.calibration.read(path)
        print('Calibration was applied from '+path)
        return 'Calibration was applied from '+path

    @pipe
    def info(self):
        return ('Information', 
                dict(developer='Alexey Melnikov',
                    contact='alexey0703@esrf.fr',
                    model='nanocal 2.0',
                    version_number=0.1))

    # ===================================
    # Calibration

    @command
    def apply_default_calibration(self):
        return self.change_calibration(DEFAULT_CALIBRATION_PATH)
    
    @command
    def apply_calibration(self):
        return self.change_calibration(CALIBRATION_PATH)
    
    @command
    def get_calibration_info(self):
        self.info_stream(self.calibration.comment)
        print(self.calibration.comment)
        return True

    # ===================================
    # Fast heating

    @command(dtype_in=[float])
    def set_fh_time_profile(self, time_table):
        self.time_temp_table['time'] = time_table
    
    @command(dtype_in=[float])
    def set_fh_temp_profile(self, temp_table):
        self.time_temp_table['temperature'] = temp_table

    @command
    def arm_fast_heat(self):
        with FastHeat(self.time_temp_table, self.calibration) as fh:
            self.voltage_profiles = fh.arm()
    
    @command
    def run_fast_heat(self):
        with FastHeat(self.time_temp_table, self.calibration) as fh:
            fh.run(self.voltage_profiles)


if __name__=='__main__':
    NanoControl.run_server()

    