from daq_device import DaqDeviceHandler
from ai_device import AiDeviceHandler
from ao_device import AoDeviceHandler
from ao_data_generators import ScanDataGenerator
from settings import SettingsParser
from constants import SETTINGS_PATH

import pandas as pd
import uldaq as ul


class ExperimentManager:
    def __init__(self):      
        self._apply_settings()

        # making empty DF and empty file for data saving
        # later store data in ai_data and throw it into *h5 file
        self.ai_data = pd.DataFrame()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))
        if self._daq_device_handler:
            if self._ai_device_handler.status() == ul.ScanStatus.RUNNING:
                self._ai_device_handler.stop()
            if self._ao_device_handler.status() == ul.ScanStatus.RUNNING:
                self._ao_device_handler.stop()
            if self._daq_device_handler.is_connected():
                self._daq_device_handler.disconnect()
            self._daq_device_handler.release()
        # TODO: maybe add here dumping into h5 file??  # @EK: seems quite reasonable

    def get_ai_data(self):
        """Provides explicit access to the read ai_data."""
        return self.ai_data
    
    def _apply_settings(self):
        self._settings = SettingsParser(SETTINGS_PATH)
        self._daq_params = self._settings.get_daq_params()
        self._ai_params = self._settings.get_ai_params()
        self._ao_params = self._settings.get_ao_params()

    def run(self):
        self._daq_device_handler = DaqDeviceHandler(self._daq_params)
        if not self._daq_device_handler.is_connected():
            self._daq_device_handler.connect()

    # for limited scans (one AO buffer will be applied)
    def ao_scan(self, voltage_profiles: dict):
        print("AO SCAN mode. Wait until scan is finished.\n")
        self._ao_params.options = 2 # ul.ScanOption.BLOCKIO
        
        self._ao_buffer = ScanDataGenerator(voltage_profiles,
                                            self._ao_params.low_channel,
                                            self._ao_params.high_channel).buffer

        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(),
                                                  self._ao_params)
        # need to stop AO before scan
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()

        self._ao_device_handler.scan(self._ao_buffer)

    # for setting voltage
    def ao_set(self, channel_voltages: dict, duration: int):
        print("AO PULSE mode.\n")
        # TODO: set specified voltage on selected channels + sine on reference channel
        pass

    # for continuous scans (ao buffer will be repeated)
    def ao_continuous(self, voltage_profiles: dict):
        self._ao_params.options = 8  # ul.ScanOption.CONTINUOUS
        # TODO: think about difference with ao_set, maybe leave just one of them
        pass

    def ai_continuous(self, ai_channels_to_read: list,
                      SAVE_DATA: bool):
        # AI buffer is 1 s and AI is made in loop. AO buffer equals to AO profile length.
        self._ai_params.options = 8  # ul.ScanOption.CONTINUOUS
        self._ai_device_handler = AiDeviceHandler(self._daq_device_handler.get_ai_device(),
                                                  self._ai_params)
        # need to stop acquisition before scan
        if self._ai_device_handler.status == ul.ScanStatus.RUNNING:
            self._ai_device_handler.stop()
        self._ai_device_handler.scan()

        if SAVE_DATA:
            self.ai_data.to_hdf('./data/raw_data.h5', key='dataset', format='table', mode='w')
        self._read_data_loop(ai_channels_to_read,
                            self._ai_device_handler,
                            self._ao_device_handler,
                            SAVE_DATA = True)

        
    def _read_data_loop(self, ai_channels_to_read: list, 
                        ai_device_handler: AiDeviceHandler,
                        ao_device_handler: AoDeviceHandler,
                        SAVE_DATA: bool):
        try:
            _temp_ai_data = ai_device_handler.data()

            _HIGH_HALF_FLAG = True
            _half_buffer_length = int(len(_temp_ai_data)/2)
            _step = ai_device_handler.channel_count
            _one_channel_half_buffer_length = int(_half_buffer_length / _step)
            _index = 0

            while True:
                try:
                    # Get background operations statuses
                    ai_status, ai_transfer_status = ai_device_handler.status()
                    ao_status, ao_transfer_status = ao_device_handler.status()

                    _ai_index = ai_transfer_status.current_index

                    if _ai_index > _half_buffer_length and _HIGH_HALF_FLAG:
                        # reading low half 
                        # print('reading low half. index=', _ai_index)
                        _HIGH_HALF_FLAG, _index = self._read_half_buffer(_temp_ai_data, 
                                                            ai_channels_to_read,
                                                            _HIGH_HALF_FLAG, _half_buffer_length, 
                                                            _step, _index, _one_channel_half_buffer_length,
                                                            SAVE_DATA)
                             
                    elif _ai_index < _half_buffer_length and not _HIGH_HALF_FLAG:
                        # reading high half
                        # print('reading high half. index=', _ai_index)
                        _HIGH_HALF_FLAG, _index = self._read_half_buffer(_temp_ai_data, 
                                                            ai_channels_to_read,
                                                            _HIGH_HALF_FLAG, _half_buffer_length, 
                                                            _step, _index, _one_channel_half_buffer_length,
                                                            SAVE_DATA)
                    
                    if (ao_status != ul.ScanStatus.RUNNING):
                        self._ai_device_handler.stop()
                        break  
                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            print('Acquisition aborted')
            pass
    
    def _read_half_buffer(self, temp_ai_data, ai_channels_to_read: list,
                        HIGH_HALF_FLAG: bool, half_buffer_length: int, 
                        step: int, index: int, one_channel_half_buffer_length: int,
                        SAVE_DATA: bool):
        if HIGH_HALF_FLAG == True:
            df = pd.DataFrame(temp_ai_data[:half_buffer_length])
            HIGH_HALF_FLAG = False
        else:
            df = pd.DataFrame(temp_ai_data[half_buffer_length:])
            HIGH_HALF_FLAG = True

        multi_index = pd.MultiIndex.from_product([list(range(index, one_channel_half_buffer_length+index)), 
                                                list(range(step))])
        df.index = multi_index
        df = df.unstack()
        df.columns = df.columns.droplevel()
        df = df[ai_channels_to_read]
        self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
        if SAVE_DATA:
            df.to_hdf('./data/raw_data.h5', key='dataset', format='table', append=True, mode='a')
        index += one_channel_half_buffer_length

        return HIGH_HALF_FLAG, index

