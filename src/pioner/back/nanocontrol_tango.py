import json
import logging
import os
# Use mock uldaq for development without hardware
from .mock_uldaq import uldaq as ul
from tango.server import AttrWriteType, Device, attribute, command, pipe

from pioner.shared.constants import *
from pioner.shared.calibration import Calibration
from pioner.shared.settings import BackSettings
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.fastheat import FastHeat
from pioner.back.iso_mode import IsoMode


class NanoControl(Device):
    """General class to control DAQ device using TANGO server.
    To launch server manually use the command
    :obj:`python nanocontrol_tango.py NanoControl`
    """
    _fh: FastHeat

    def init_device(self):
        """Method to initialize the server and apply default 
        configuration settings.

        - sets path for logging  

        - sets path for data saving  

        - applies default calibration  

        - parses :obj:`*json` settings file  

        - makes :obj:`pioner.back.daq_device.DaqDeviceHandler` instance with parsed settings
        """
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

        self._settings = BackSettings(SETTINGS_FILE_REL_PATH)
        daq_params = self._settings.daq_params
        self._daq_device_handler = DaqDeviceHandler(daq_params)
        logging.info('TANGO: Initial setup done.')

    @command
    def set_connection(self):
        """ Tango :obj:`command` method to set connection to available DAQ device
        using method :obj:`try_connect` of :obj:`pioner.back.daq_device.DaqDeviceHandler`.
        Logs result even in case of error.
        """
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
    def disconnect(self):
        """ Tango :obj:`command` method to disconnect DAQ device
        using method :obj:`disconnect` of :obj:`pioner.back.daq_device.DaqDeviceHandler`.
        Logs result.
        """
        self._daq_device_handler.disconnect()
        logging.info('TANGO: Successfully disconnected.')

    @pipe
    def get_info(self):
        """ Tango :obj:`pipe` method to get information of the software.

        Returns
        ---------
            :obj:`dict` 
                :obj:`{developer:'str', contact:'str', model:'str', version_number:'float'}`
        """
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
        """ Tango :obj:`command` method to load temperature-voltage calibration.
        Loads calibration coefficients from string and writes them to :obj:`*.json` file.
        
        Args
        ------  
            str_calib : :obj:`str`
                Calibration coefficients in string format. For more information refer to 
                :obj:`pioner.shared.calibration.Calibration.get_str`
        """
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(json.loads(str_calib), f, separators=(',', ': '), indent=4)
            logging.info('TANGO: Calibration file {} was updated from external file.'.format(CALIBRATION_FILE))

    @command
    def apply_default_calibration(self):
        """ Tango :obj:`command` method to apply default temperature-voltage calibration.
        Reads calibration coefficients from :obj:`*.json` file.
        """
        try:
            self._calibration.read(DEFAULT_CALIBRATION_FILE)
            logging.info('TANGO: Calibration was applied from {}'.format(DEFAULT_CALIBRATION_FILE))
        except Exception as e:
            logging.error("TANGO: Error while applying default calibration: {}.".format(e))

    @command
    def apply_calibration(self):
        """ Tango :obj:`command` method to apply custom temperature-voltage calibration.
        Reads calibration coefficients from :obj:`*.json` file.
        """
        try:
            self._calibration.read(CALIBRATION_FILE)
            logging.info('TANGO: Calibration was applied from {}'.format(CALIBRATION_FILE))
        except Exception as e:
            logging.error("TANGO: ERROR. Exception while applying calibration: {}.".format(e))

    @pipe(label="Current calibration")
    def get_current_calibration(self):
        """ Tango :obj:`pipe` method to get current calibration as dictionary.

        Returns
        ---------
            :obj:`dict` 
                Uses :obj:`pioner.shared.calibration.Calibration.get_str` 
                and transforms string to dictionary. Use key :obj:`calib` to access calibration
        """
        self.__calib_dict = 'calib', dict(calib=self._calibration.get_str())
        return self.__calib_dict

    # ===================================
    # Settings
    @pipe(label="Current sample rate")
    def get_sample_rate(self):
        """ Tango :obj:`pipe` method to get current applied sample rate.

        Returns
        ---------
            :obj:`dict` 
                Use key :obj:`sr` to access sampling rate
        """
        self.__sr = 'sr', dict(sr=self._settings.ai_params.sample_rate)
        return self.__sr

    @command(dtype_in=int)
    def set_sample_scan_rate(self, scan_rate):
        """ Tango :obj:`command` method to set sample rate. Logs if success.

        Args
        ------  
            scan_rate : :obj:`int`
                Sample rate in points per second.
        """
        self._settings.ai_params.sample_rate = scan_rate
        self._settings.ao_params.sample_rate = scan_rate
        logging.info("TANGO: Sample scan rate changed to: {}".format(scan_rate))
    
    @command
    def reset_sample_scan_rate(self):
        """ Tango :obj:`command` method to reset sample rate, the value 
        is parsed from :obj:`*.json` settings file.
        """
        self._settings.parse_ai_params()
        self._settings.parse_ao_params()

    # ===================================
    # Fast heating

    @command(dtype_in=str)
    def arm_fast_heat(self, time_temp_volt_tables_str):
        """ Tango :obj:`command` method to prepare (arm) fast heating profile.
        Makes :obj:`pioner.back.fastheat.FastHeat` instance and uses
        :obj:`pioner.back.fastheat.FastHeat.arm` method. Logs result.
            
        Args
        ------              
            time_temp_volt_tables_str : :obj:`str`
                Dictionary :obj:`time_temp_volt_tables`, 
                accepted by :obj:`pioner.back.fastheat.FastHeat` should be 
                converted into string before passing as an argument.
        """
        self._time_temp_volt_tables = json.loads(time_temp_volt_tables_str)
        self._fh = FastHeat(self._daq_device_handler, self._settings,
                            self._time_temp_volt_tables, self._calibration,
                            ai_channels = [0,1,3,4,5],
                            FAST_HEAT_CUSTOM_FLAG=False)
        self._fh.arm()
        logging.info("TANGO: Fast heating armed.")

    @command
    def run_fast_heat(self):
        """ Tango :obj:`command` method to apply (run) fast heating profile.
        Checks if fast heating is prepared correctly (armed) and uses
        :obj:`pioner.back.fastheat.FastHeat.run` method. Logs result.
        """
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
        """ Tango :obj:`command` method to prepare (arm) isotherm / iso-voltage mode.
        Makes :obj:`pioner.back.iso_mode.IsoMode` instance and uses
        :obj:`pioner.back.iso_mode.IsoMode.arm` method. Logs result.
            
        Args
        ------              
            chan_temp_volt_str : :obj:`str`
                Dictionary :obj:`chan_temp_volt`, 
                accepted by :obj:`pioner.back.iso_mode.IsoModes` should be 
                converted into string before passing as an argument.
        """
        self._chan_temp_volt = json.loads(chan_temp_volt_str)
        self._im = IsoMode(self._daq_device_handler, self._settings,
                            self._chan_temp_volt, self._calibration)
        channel, voltage = self._im.arm()
        logging.info("TANGO: Static (iso) mode armed at channel {} with {} V.".format(channel, voltage))

    @command
    def run_iso_mode(self):
        """ Tango :obj:`command` method to apply (run) fast isotherm / iso-voltage mode.
        Checks if iso mode is prepared correctly (armed) and uses
        :obj:`pioner.back.iso_mode.IsoMode.run` method. Logs result.
        """
        if self._im.is_armed():
            self._im.run(do_ai=True)
        else:
            logging.warning("TANGO: WARNING. Static (iso) mode cannot be started, since it should be armed first.")
        

    # @command 
    # def stop_ai(self):
    #     # self._im.ai_stop()
    #     logging.info("TANGO: test")
    #     # self._daq_device_handler.get_ai_device.scan_stop()
        

if __name__ == '__main__':
    NanoControl.run_server()
