from tango.server import Device, attribute, pipe, command, AttrWriteType
from constants import (CALIBRATION_PATH, DEFAULT_CALIBRATION_PATH, LOGS_FOLDER_REL_PATH, RAW_DATA_FOLDER_REL_PATH,
                       NANOCONTROL_LOG_FILE_REL_PATH, SETTINGS_PATH)
from calibration import Calibration
from fastheat import FastHeat
from settings import SettingsParser
from daq_device import DaqDeviceHandler

import uldaq as ul
import logging
import os


class NanoControl(Device):
    _fh: FastHeat

    def init_device(self):
        Device.init_device(self)
        self._do_initial_setup()

    def _do_initial_setup(self):
        if not (os.path.exists(LOGS_FOLDER_REL_PATH)):
            os.makedirs(LOGS_FOLDER_REL_PATH)
        if not (os.path.exists(RAW_DATA_FOLDER_REL_PATH)):
            os.makedirs(RAW_DATA_FOLDER_REL_PATH)

        logging.basicConfig(filename=NANOCONTROL_LOG_FILE_REL_PATH, encoding='utf-8', level=logging.DEBUG,
                            filemode="w", format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S')

        self._calibration = Calibration()
        self.apply_default_calibration()
        self._time_temp_table = dict(time=[], temperature=[])

        self._settings_parser = SettingsParser(SETTINGS_PATH)
        daq_params = self._settings_parser.get_daq_params()
        self._daq_device_handler = DaqDeviceHandler(daq_params)
        logging.info('Initial setup done.')

    @command
    def set_connection(self):
        try:
            self._daq_device_handler.try_connect()
            logging.info('Successfully connected.')
        except ul.ULException as e:
            logging.error("Error while setting connection."
                          "Code: {}, message: {}.".format(e.error_code, e.error_message))
        except TimeoutError as e:
            logging.error("Error while setting connection: {}".format(e))
        finally:
            self._daq_device_handler.quit()

    @command
    def reset_connection(self):
        self._daq_device_handler.reset()
        logging.info('Connection has been reset.')

    @command
    def log_device_info(self):
        try:
            descriptor = self._daq_device_handler.get_descriptor()
            logging.info("Product info: {}".format(descriptor.dev_string))
            logging.info("Interface type: {}".format(descriptor.dev_interface))
        except ul.ULException as e:
            logging.error("Error while logging info."
                          "Code: {}, message: {}.".format(e.error_code, e.error_message))

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
        try:
            self._calibration.read(DEFAULT_CALIBRATION_PATH)
            logging.info('Calibration was applied from {}'.format(DEFAULT_CALIBRATION_PATH))
        except Exception as e:
            logging.error("Error while applying default calibration: {}.".format(e))

    @command
    def apply_calibration(self):
        try:
            self._calibration.read(CALIBRATION_PATH)
            logging.info('Calibration was applied from {}'.format(CALIBRATION_PATH))
        except Exception as e:
            logging.error("Error while applying calibration: {}.".format(e))

    @pipe
    def get_calibration(self):
        return ('Calibration',
                dict(comment=self._calibration.comment))

    # ===================================
    # Fast heating

    @command(dtype_in=[float])
    def set_fh_time_profile(self, time_table):
        self._time_temp_table['time'] = time_table
        logging.info("Fast heating time profile was set to: [{}]".format('   '.join(map(str, time_table))))

    @command(dtype_in=[float])
    def set_fh_temp_profile(self, temp_table):
        self._time_temp_table['temperature'] = temp_table
        logging.info("Fast heating temperature profile was set to: [{}]".format('   '.join(map(str, temp_table))))

    @command
    def arm_fast_heat(self):
        self._fh = FastHeat(self._daq_device_handler, self._settings_parser,
                            self._time_temp_table, self._calibration)
        self._fh.arm()
        logging.info("Fast heating armed.")

    @command
    def run_fast_heat(self):
        if self._fh.is_armed():
            logging.info("Fast heating started.")
            self._fh.run()
            logging.info("Fast heating finished.")
        else:
            logging.warning("Fast heating cannot be started, since it should be armed first.")


if __name__ == '__main__':
    NanoControl.run_server()
