from daq_device import DaqDeviceHandler
from ai_device import AiDeviceHandler
from ao_device import AoDeviceHandler
from ao_data_generators import ScanDataGenerator
from settings import SettingsParser
from constants import SETTINGS_PATH, RAW_DATA_PATH

import pandas as pd
import uldaq as ul
import os
import glob


class ExperimentManager:
    def __init__(self):      
        self._apply_settings()

    def get_ai_data(self, ai_channels : list):
        fpath = RAW_DATA_PATH+'raw_data.h5'
        df = pd.read_hdf(fpath, key='dataset')

        chan_num = self._ai_params.high_channel - self._ai_params.low_channel + 1
        one_chan_len = int(len(df) / chan_num)
        multi_index = pd.MultiIndex.from_product([list(range(one_chan_len)), list(range(chan_num))])
        df.index = multi_index
        df = df.unstack()
        df.columns = df.columns.droplevel()
        df = df[ai_channels]
        
        return df
    
    def _apply_settings(self):
        self._settings = SettingsParser(SETTINGS_PATH)
        self._daq_params = self._settings.get_daq_params()
        self._ai_params = self._settings.get_ai_params()
        self._ao_params = self._settings.get_ao_params()

    def run(self):
        self._daq_device_handler = DaqDeviceHandler(self._daq_params)
        if not self._daq_device_handler.is_connected():
            self._daq_device_handler.connect()

        # Strange, but the first invoke of pandas.to_hdf takes a lot of time. 
        # So in order not to loose points during aquisition, we invoke it here with empty dataframe
        df = pd.DataFrame([])
        fpath = RAW_DATA_PATH+'raw_data.h5'
        df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')

        # before starting, removing the previous generated files with data from separated buffers
        files = glob.glob(RAW_DATA_PATH+'raw_data_buffer_'+'*.h5', recursive=True)
        files.append(RAW_DATA_PATH+'raw_data.h5')
        for f in files:
            try: os.remove(f)
            except: pass
        

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

    def ai_continuous(self, SAVE_DATA: bool):
        # AI buffer is 1 s and AI is made in loop. AO buffer equals to AO profile length.
        self._ai_params.options = 8  # ul.ScanOption.CONTINUOUS
        self._ai_device_handler = AiDeviceHandler(self._daq_device_handler.get_ai_device(),
                                                  self._ai_params)
        # need to stop acquisition before scan
        if self._ai_device_handler.status == ul.ScanStatus.RUNNING:
            self._ai_device_handler.stop()
        self._ai_device_handler.scan()
        self._read_data_loop(SAVE_DATA = True)

        print('Continuous AI finished!')
        
    def _read_data_loop(self, SAVE_DATA: bool):
        try:
            _temp_ai_data = self._ai_device_handler.data()

            _HIGH_HALF_FLAG = True
            _half_buffer_length = int(len(_temp_ai_data)/2)
            _buffer_index = 0
            _buffers_num = int(len(self._ao_buffer)/(self._ao_params.sample_rate* \
                            (self._ao_params.high_channel-self._ao_params.low_channel+1)))

            if not os.path.exists(RAW_DATA_PATH): 
                os.makedirs(RAW_DATA_PATH)

            while True:
                try:
                    # Get ai operation statuse and index
                    _, ai_transfer_status = self._ai_device_handler.status()
                    _ai_index = ai_transfer_status.current_index

                    if _buffer_index >= _buffers_num:
                        self._ai_device_handler.stop()
                        fpath = RAW_DATA_PATH+'raw_data.h5'
                        for i in list(range(_buffers_num)):
                            buf_path = RAW_DATA_PATH+'raw_data_buffer_'+str(i)+'.h5'
                            df = pd.read_hdf(buf_path, key='dataset')
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
                        break  

                    if _ai_index > _half_buffer_length and _HIGH_HALF_FLAG:
                        # reading low half 
                        print('reading low half. index =', _ai_index, '. Buffer index is: ', _buffer_index)
                        df = pd.DataFrame(_temp_ai_data[:_half_buffer_length]) 
                        if SAVE_DATA:
                            fpath = RAW_DATA_PATH+'raw_data_buffer_'+str(_buffer_index)+'.h5'
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
                        _HIGH_HALF_FLAG = False
                             
                    elif _ai_index < _half_buffer_length and not _HIGH_HALF_FLAG:
                        # reading high half
                        print('reading high half. index =', _ai_index, '. Buffer index is: ', _buffer_index)
                        df = pd.DataFrame(_temp_ai_data[_half_buffer_length:])
                        if SAVE_DATA:
                            fpath = RAW_DATA_PATH+'raw_data_buffer_'+str(_buffer_index)+'.h5'
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
                        _HIGH_HALF_FLAG = True
                        _buffer_index += 1
                
                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            print('Acquisition aborted')
            pass

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