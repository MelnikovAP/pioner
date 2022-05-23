from daq_device import DaqDeviceHandler, DaqParams
from ai_device import AiDeviceHandler, AiParams
from ao_device import AoDeviceHandler, AoParams
from ao_data_generators import ScanDataGenerator
from settings import SettingsParser
from constants import SETTINGS_PATH

from time import sleep
import pandas as pd
import uldaq as ul
import sys

class ExperimentManager:
    def __init__(self):      
        self.apply_settings()

        # making empty DF and empty file for data saving
        # later store data in ai_data and throw it into *h5 file
        self.ai_data = pd.DataFrame()
        self.ai_data.to_hdf('./data/raw_data.h5', key='dataset', format='table', mode='w')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))
        if self.daq_device_handler:
            if self.ai_device_handler.status() == ul.ScanStatus.RUNNING:
                self.ai_device_handler.stop()
            if self.ao_device_handler.status() == ul.ScanStatus.RUNNING:
                self.ao_device_handler.stop()
            if self.daq_device_handler.is_connected():
                self.daq_device_handler.disconnect()
            self.daq_device_handler.release()
        # maybe add here dumping into h5 file??

    def get_ai_data(self):
        """Provides explicit access to the read ai_data."""
        return self.ai_data
    
    def apply_settings(self):
        self.settings = SettingsParser(SETTINGS_PATH)
        self.daq_params = self.settings.get_daq_params()
        self.ai_params = self.settings.get_ai_params()
        self.ao_params = self.settings.get_ao_params()

    def run(self):
        self.daq_device_handler = DaqDeviceHandler(self.daq_params)
        if not self.daq_device_handler.is_connected():
            self.daq_device_handler.connect()

    # for limited scans (one ao buffer will be applied)
    def ao_scan(self, voltage_profiles: dict):
        print("AO SCAN  mode. Wait util scan is finished.\n")
        self.ao_params.options = 2 # ul.ScanOption.BLOCKIO

        self._ao_buffer = ScanDataGenerator(voltage_profiles,
                                self.ao_params.low_channel,
                                self.ao_params.high_channel).buffer

        self.ao_device_handler = AoDeviceHandler(self.daq_device_handler.get_ao_device(),
                                                self.ao_params)
        # need to stop ao before scan
        if self.ao_device_handler.status == ul.ScanStatus.RUNNING:
            self.ao_device_handler.stop()

        self.ao_device_handler.scan(self._ao_buffer)

    # for setting voltage
    def ao_set(self, channel_voltages: dict, duration: int):
        print("AO PULSE mode.\n")
        # TODO: set specified voltage on selected channels + sinus on reference channel
        pass

    # for continuous scans (ao buffer will be repeated)
    def ao_continuous(self, voltage_profiles: dict):
        self.ao_params.options = 8  # ul.ScanOption.CONTINUOUS
        # TODO: think about difference with ao_set, maybe leave just one of them
        pass

    def ai_continuous(self, ai_channels_to_read: list,
                        SAVE_DATA: bool):
        # Ai buffer is 1 s and ai is made in loop. Ao buffer equals to ao profile length
        self.ai_params.options = 8  # ul.ScanOption.CONTINUOUS
        self.ai_device_handler = AiDeviceHandler(self.daq_device_handler.get_ai_device(),
                                                self.ai_params)
        # need to stop aquisition before scan
        if self.ai_device_handler.status == ul.ScanStatus.RUNNING:
            self.ai_device_handler.stop()    
        self.ai_device_handler.scan()

        if SAVE_DATA == True:
            self._save_data_loop(ai_channels_to_read, 
                                self.ai_device_handler, 
                                self.ao_device_handler)

        
    def _save_data_loop(self, ai_channels_to_read: list, 
                        ai_device_handler: AiDeviceHandler,
                        ao_device_handler: AoDeviceHandler):
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
                        print('reading low half ')
                        df = pd.DataFrame(_temp_ai_data[:_half_buffer_length])
                        multi_index = pd.MultiIndex.from_product([list(range(_index, _one_channel_half_buffer_length+_index)), 
                                                                list(range(_step))])
                        df.index = multi_index
                        df = df.unstack()
                        df.columns = df.columns.droplevel()
                        df = df[ai_channels_to_read]
                        self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
                        df.to_hdf('./data/raw_data.h5', key='dataset', format='table', append=True, mode='a')
                        _index += _one_channel_half_buffer_length
                        _HIGH_HALF_FLAG = False
                             
                    elif _ai_index < _half_buffer_length and not _HIGH_HALF_FLAG:
                        # reading high half
                        print('reading high half')
                        df = pd.DataFrame(_temp_ai_data[_half_buffer_length:])
                        multi_index = pd.MultiIndex.from_product([list(range(_index, _one_channel_half_buffer_length+_index)), 
                                                                list(range(_step))])
                        df.index = multi_index
                        df = df.unstack()
                        df.columns = df.columns.droplevel()
                        df = df[ai_channels_to_read]
                        self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
                        df.to_hdf('./data/raw_data.h5', key='dataset', format='table', append=True, mode='a')
                        _index += _one_channel_half_buffer_length
                        _HIGH_HALF_FLAG = True
                    
                    if (ao_status != ul.ScanStatus.RUNNING):
                        # TODO: correct aborting the scan. now it is not fully saved. 
                        
                        # print('reading last high half')
                        # print(ai_status)
                        # print(ao_status)
                        # reading last high half if the last reading was in the low half
                        # if not _HIGH_HALF_FLAG:
                        #     df = pd.DataFrame(_temp_ai_data[_half_buffer_length:])
                        #     multi_index = pd.MultiIndex.from_product([list(range(_index, _one_channel_half_buffer_length+_index)), 
                        #                                             list(range(_step))])
                        #     df.index = multi_index
                        #     df = df.unstack()
                        #     df.columns = df.columns.droplevel()
                        #     df = df[ai_channels_to_read]
                        #     self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
                        #     df.to_hdf('.raw_data.h5', key='dataset', format='table', append=True, mode='a')
                        break  

                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            print('Acquisition aborted')
            pass
