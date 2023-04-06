from tango.server import Device, pipe, command
from calibration import Calibration
from fastheat import FastMode
from iso_mode import IsoMode
from settings import Settings
from daq_device import DaqDeviceHandler
from utils.constants import *

import uldaq as ul
import logging
import os
import json


class NanoControl(Device):
    _fh: FastMode

    def init_device(self):
        Device.init_device(self)
        self._do_initial_setup()

    def _do_initial_setup(self):
        if not (os.path.exists(LOGS_FOLDER_REL_PATH)):
            os.makedirs(LOGS_FOLDER_REL_PATH)
        if not (os.path.exists(RAW_DATA_FOLDER_REL_PATH)):
            os.makedirs(RAW_DATA_FOLDER_REL_PATH)

        logging.basicConfig(filename=NANOCONTROL_LOG_FILE_REL_PATH, encoding='utf-8', level=logging.DEBUG,
                            filemode="w", format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S')  # TODO: remove from class

        self._calibration = Calibration()
        self.apply_default_calibration()
        self._time_temp_table = dict(time=[], temperature=[])

        self._settings = Settings(SETTINGS_PATH)
        daq_params = self._settings.daq_params
        self._daq_device_handler = DaqDeviceHandler(daq_params)
        logging.info('TANGO: Initial setup done.')

    @command
    def set_connection(self):
        try:
            self._daq_device_handler.try_connect()
            logging.info('TANGO: Successfully connected.')
        except ul.ULException as e:
            logging.error("TANGO: ERROR. ULException while setting connection."
                          "Code: {}, message: {}.".format(e.error_code, e.error_message))
            self._daq_device_handler.quit()
        except TimeoutError as e:
            logging.error("TANGO: ERROR. Timeout exception while setting connection: {}".format(e))
            self._daq_device_handler.quit()

    @command
    def reset_connection(self):
        self._daq_device_handler.reset()
        logging.info('TANGO: Connection has been reset.')

    @command
    def disconnect(self):
        self._daq_device_handler.disconnect()
        logging.info('TANGO: Successfully disconnected.')
        # self._daq_device_handler.release()

    @command
    def log_device_info(self):
        try:
            descriptor = self._daq_device_handler.get_descriptor()
            logging.info("TANGO: Product info: {}".format(descriptor.dev_string))
            logging.info("TANGO: Interface type: {}".format(descriptor.dev_interface))
        except ul.ULException as e:
            logging.error("TANGO: ERROR. Exception while logging info."
                          "Code: {}, message: {}.".format(e.error_code, e.error_message))

    @pipe
    def get_info(self):
        return ('Information',
                dict(developer='Alexey Melnikov & Evgenii Komov',
                     contact='alexey0703@esrf.fr',
                     model='nanocal 2.0',
                     version_number=0.1
                     )
                )

    # ===================================
    # Calibration

    @command(dtype_in=str)
    def load_calibration(self, str_calib):
        with open(CALIBRATION_PATH, 'w') as f:
            json.dump(json.loads(str_calib), f, separators=(',', ': '), indent=4)
            logging.info('TANGO: Calibration file {} was updated from external file.'.format(CALIBRATION_PATH))

    @command
    def apply_default_calibration(self):
        try:
            self._calibration.read(DEFAULT_CALIBRATION_PATH)
            logging.info('TANGO: Calibration was applied from {}'.format(DEFAULT_CALIBRATION_PATH))
        except Exception as e:
            logging.error("TANGO: Error while applying default calibration: {}.".format(e))

    @command
    def apply_calibration(self):
        try:
            self._calibration.read(CALIBRATION_PATH)
            logging.info('TANGO: Calibration was applied from {}'.format(CALIBRATION_PATH))
        except Exception as e:
            logging.error("TANGO: ERROR. Exception while applying calibration: {}.".format(e))

    @pipe(label="Current calibration")
    def get_current_calibration(self):
        self.__calib_dict = 'calib', dict(calib=self._calibration.get_str())
        return self.__calib_dict

    # ===================================
    # Settings
    @pipe(label="Current sample rate")
    def get_sample_rate(self):
        self.__sr = 'sr', dict(sr=self._settings.ai_params.sample_rate)
        return self.__sr

    @command(dtype_in=int)
    def set_sample_scan_rate(self, scan_rate):
        self._settings.ai_params.sample_rate = scan_rate
        self._settings.ao_params.sample_rate = scan_rate
        logging.info("TANGO: Sample scan rate changed to: {}".format(scan_rate))
    
    @command
    def reset_sample_scan_rate(self):
        self._settings.parse_ai_params()
        self._settings.parse_ao_params()
    
    # @command(dtype_in=[float])
    # def set_modulation_parameters(self, params):
    #     self._settings.modulation_frequency = params[0]
    #     self._settings.modulation_amplitude = params[1]
    #     self._settings.modulation_offset = params[2]

    # ===================================
    # Fast heating

    @command(dtype_in=str)
    def arm_fast_heat(self, time_temp_volt_tables_str):
        self._time_temp_volt_tables = json.loads(time_temp_volt_tables_str)
        self._fh = FastMode(self._daq_device_handler, self._settings,
                            self._time_temp_volt_tables, self._calibration,
                            ai_channels = [0,1,3,4,5],
                            FAST_HEAT_CUSTOM_FLAG=False)
        self._fh.arm()
        logging.info("TANGO: Fast heating armed.")

    @command
    def run_fast_heat(self):
        if self._fh.is_armed():
            logging.info("TANGO: Fast heating started.")
            self._fh.run()
            
            logging.info("TANGO: Fast heating finished.")
        else:
            logging.warning("TANGO: WARNING. Fast heating cannot be started, since it should be armed first.")


    # ===================================
    # Iso (set) mode
    
    @command(dtype_in=str)
    def arm_iso_mode(self, chan_temp_volt_str):
        self._chan_temp_volt = json.loads(chan_temp_volt_str)
        self._im = IsoMode(self._daq_device_handler, self._settings,
                            self._chan_temp_volt, self._calibration)
        channel, voltage = self._im.arm()
        logging.info("TANGO: Static (iso) mode armed at channel {} with {} V.".format(channel, voltage))

    @command
    def run_iso_mode(self):
        if self._im.is_armed():
            self._im.run(do_ai=True)
        else:
            logging.warning("TANGO: WARNING. Static (iso) mode cannot be started, since it should be armed first.")
        

    @command 
    def stop_ai(self):
        # self._im.ai_stop()
        logging.info("TANGO: test")
        # self._daq_device_handler.get_ai_device.scan_stop()
        

if __name__ == '__main__':
    NanoControl.run_server()
