from daq_device import DaqDeviceHandler, DaqParams
from ai_device import AiDeviceHandler, AiParams
from ao_device import AoDeviceHandler, AoParams
from ao_data_generators import PulseDataGenerator

from time import sleep
import pandas as pd
import uldaq as ul
import sys

class ExperimentManager:
    def __init__(self, voltage_profiles: dict, 
                ai_channels: list,
                daq_params: DaqParams,
                ai_params: AiParams, 
                ao_params: AoParams):
        self._voltage_profiles = voltage_profiles
        self._ai_channels = ai_channels
        self._daq_params = daq_params
        self._ai_params = ai_params
        self._ao_params = ao_params

        # making empty DF and empty file for data saving
        # later store data in ai_data and throw it into *h5 file
        self.ai_data = pd.DataFrame()
        self.ai_data.to_hdf('.raw_data.h5', key='dataset', format='table', mode='w')

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

    def run(self):
        self.daq_device_handler = DaqDeviceHandler(self._daq_params)
        self.daq_device_handler.connect()

        # for pulses in both ao and ai
        if self._ai_params.options==2 and self._ao_params.options==2:
            print("BLOCKIO  mode. Wait util scan is finished.\n")
            self._ao_buffer = PulseDataGenerator(self._voltage_profiles,
                                    self._ao_params.low_channel,
                                    self._ao_params.high_channel).buffer
            self.ai_device_handler = AiDeviceHandler(self.daq_device_handler.get_ai_device(),
                                                    self._ai_params)
            self.ao_device_handler = AoDeviceHandler(self._ao_buffer, 
                                                    self.daq_device_handler.get_ao_device(),
                                                    self._ao_params)
            self.ai_device_handler.scan_finite()
            self.ao_device_handler.scan_finite()
            
            self.ai_data = self.save_data_finite(self._ai_channels, 
                                                self.ai_device_handler, 
                                                self.ao_device_handler)

        # for continuous scan in both ao and ai
        if self._ai_params.options==8 and self._ao_params.options==8:
            print("CONTINUOUS mode. To be developed. For exit use Ctrl+C\n")
            pass
    
    def save_data_finite(self, ai_channels: list, 
                        ai_device_handler: AiDeviceHandler,
                        ao_device_handler: AoDeviceHandler):
        df = pd.DataFrame(ai_device_handler.data()[:])
        _step = ai_device_handler.channel_count
        multi_index = pd.MultiIndex.from_product([list(range(int(len(df)/_step))), list(range(_step))])
        df.index = multi_index
        df = df.unstack()
        df.columns = df.columns.droplevel()
        df.to_hdf('.raw_data.h5', key='dataset', format='table', append=True, mode='w')
        return df


    def save_data_infinite(self, ai_channels: list, 
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
                        df = df[self._ai_channels]
                        self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
                        df.to_hdf('.raw_data.h5', key='dataset', format='table', append=True, mode='a')
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
                        df = df[self._ai_channels]
                        self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
                        df.to_hdf('.raw_data.h5', key='dataset', format='table', append=True, mode='a')
                        _index += _one_channel_half_buffer_length
                        _HIGH_HALF_FLAG = True
                    
                    if (ai_status != ul.ScanStatus.RUNNING) or (ao_status != ul.ScanStatus.RUNNING):
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
                        #     df = df[self._ai_channels]
                        #     self.ai_data = pd.concat([self.ai_data, df], ignore_index=True)
                        #     df.to_hdf('.raw_data.h5', key='dataset', format='table', append=True, mode='a')
                        break  

                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            print('Acquisition aborted')
            pass
