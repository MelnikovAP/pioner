from tango.server import Device, attribute, pipe, command, AttrWriteType
from constants import (CALIBRATION_PATH, DEFAULT_CALIBRATION_PATH, LOGS_FOLDER_REL_PATH, RAW_DATA_FOLDER_REL_PATH,
                       NANOCONTROL_LOG_FILE_REL_PATH, SETTINGS_PATH)
from calibration import Calibration
from fastheat import FastHeat
from settings import SettingsParser
from utils import connect_to_daq_device
from daq_device import DaqDeviceHandler

import logging
import os


class NanoControl(Device):
    def init_device(self):
        Device.init_device(self)
        # self.initial_setup()
        
    def initial_setup(self):
        if not (os.path.exists(LOGS_FOLDER_REL_PATH)):
            os.makedirs(LOGS_FOLDER_REL_PATH)
        if not (os.path.exists(RAW_DATA_FOLDER_REL_PATH)):
            os.makedirs(RAW_DATA_FOLDER_REL_PATH)
            
        logging.basicConfig(filename=NANOCONTROL_LOG_FILE_REL_PATH, encoding='utf-8', level=logging.DEBUG,
                            filemode="w", format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S')
        
        # self.calibration = Calibration()
        # self.apply_default_calibration()
        self.time_temp_table = {
            'time': [],
            'temperature': []
        }
        logging.info('Initial setup done.')

    @command
    def set_connection(self):
        self.settings_parser = SettingsParser(SETTINGS_PATH)
        self.daq_params = self.settings_parser.get_daq_params()
        logging.info(self.daq_params)
        self.daq_device_handler = DaqDeviceHandler(self.daq_params)
        # self.daq_device_handler.connect()
        logging.info('Successfully connected.')
    
    @command
    def test(self):
        logging.info(self.daq_device_handler.descriptor().product_name)

    @pipe
    def info(self):
        return ('Information',
                dict(developer='Alexey Melnikov',
                     contact='alexey0703@esrf.fr',
                     model='nanocal 2.0',
                     version_number=0.1
                     )
                )

    # ===================================
    # Calibration

    @command
    def apply_default_calibration(self):
        self.calibration.read(DEFAULT_CALIBRATION_PATH)
        logging.info('Calibration was applied from {}'.format(DEFAULT_CALIBRATION_PATH))

    @command
    def apply_calibration(self):
        self.calibration.read(CALIBRATION_PATH)
        logging.info('Calibration was applied from {}'.format(CALIBRATION_PATH))
    
    @pipe
    def get_calibration(self):
        return ('Calibration', 
                dict(comment=self.calibration.comment))

    # ===================================
    # Fast heating

    @command(dtype_in=[float])
    def set_fh_time_profile(self, time_table):
        self.time_temp_table['time'] = time_table
        logging.info("Fast heating time profile was set to: [{}]".format('   '.join(map(str, time_table))))
    
    @command(dtype_in=[float])
    def set_fh_temp_profile(self, temp_table):
        self.time_temp_table['temperature'] = temp_table
        logging.info("Fast heating temperature profile was set to: [{}]".format('   '.join(map(str, temp_table))))

    @command
    def arm_fast_heat(self):
        with FastHeat(self.daq_device_handler,
                    self.settings_parser,
                    self.time_temp_table,
                    self.calibration) as fh:
            self.voltage_profiles = fh.arm()
            logging.info("Fast heating armed")
    
    @command
    def run_fast_heat(self):
        with FastHeat(self.time_temp_table, self.calibration) as fh:
            logging.info("Fast heating started")
            fh.run(self.voltage_profiles)
            logging.info("Fast heating finished")


if __name__ == '__main__':
    NanoControl.run_server()
