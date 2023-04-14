import glob
import logging
import os
from ctypes import Array
from typing import List

import pandas as pd
import uldaq as ul
from ai_device import AiDeviceHandler
from ao_data_generators import ScanDataGenerator
from ao_device import AoDeviceHandler
from daq_device import DaqDeviceHandler

from settings import Settings
from shared.constants import *

# TODO: check why we create analog devices inside scanning methods


class ExperimentManager:
    _ai_device_handler: AiDeviceHandler
    _ao_device_handler: AoDeviceHandler
    _ao_buffer: Array[float]

    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: Settings):
        self._daq_device_handler = daq_device_handler
        self._ai_params = settings.ai_params
        self._ao_params = settings.ao_params

        ExperimentManager._do_smth_strange()  # TODO: check and try to avoid this action

    @staticmethod
    def _do_smth_strange():
        # Strange, but the first invoke of pandas.to_hdf takes a lot of time.
        # So in order not to lose points during acquisition, we invoke it here with empty dataframe
        df = pd.DataFrame([])
        df.to_hdf(RAW_DATA_FILE_REL_PATH, key='dataset', format='table', append=True, mode='a')

        # before starting, removing the previous generated files with data from separated buffers
        h5_files_to_remove_regex = RAW_DATA_FOLDER_REL_PATH + '/' + RAW_DATA_BUFFER_FILE_PREFIX + "*.h5"

        h5_files = glob.glob(h5_files_to_remove_regex, recursive=True)
        h5_files.append(RAW_DATA_FILE_REL_PATH)
        for file in h5_files:
            try:
                os.remove(file)
            except:
                pass

    def get_ai_data(self) -> pd.DataFrame:
        df = pd.DataFrame(pd.read_hdf(RAW_DATA_FILE_REL_PATH, key='dataset'))
        return df

    def _transform_ai_data(self, ai_channels: list[int], df) -> pd.DataFrame:
        channels_num = self._ai_params.high_channel - self._ai_params.low_channel + 1
        one_chan_len = int(len(df) / channels_num)
        multi_index = pd.MultiIndex.from_product([list(range(one_chan_len)), list(range(channels_num))])
        df.index = multi_index
        df = df.unstack()
        df.columns = df.columns.droplevel()
        df = df[ai_channels]
        return df

    # for limited scans (one AO buffer will be applied)
    def ao_scan(self, voltage_profiles):
        logging.info("EXPERIMENT_MANAGER: AO SCAN mode. Wait until scan is finished.\n")
        self._ao_params.options = ul.ScanOption.BLOCKIO  # 2
        
        self._ao_buffer = ScanDataGenerator(voltage_profiles,
                                            self._ao_params.low_channel,
                                            self._ao_params.high_channel).get_buffer()

        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(),
                                                  self._ao_params)
        # need to stop AO before scan
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()

        # TODO: only for testing of digital triggering. 
        # put later in separate class

        ##################################################################

        self._ao_device_handler.scan(self._ao_buffer)

    # for setting voltage
    def ao_set(self, ao_channel, voltage):
        logging.info("EXPERIMENT_MANAGER: AO STATIC (SET) mode.\n")
        self._ao_params.options = ul.ScanOption.DEFAULTIO  # 0
        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(),
                                                  self._ao_params)
        # # need to stop AO before scan
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()
        
        self._ao_device_handler.iso_mode(ao_channel, voltage)


    def ai_continuous(self, ai_channels: list[int], do_save_data: bool):
        # AI buffer is 1 s and AI is made in loop. AO buffer equals to AO profile length.
        # if do_save_data: svae all in separate buffers (for finit ai/ao scan)
        # else: dump into dummy buffer file (for endless ai scan)
        
        self._ai_params.options = ul.ScanOption.CONTINUOUS  # 8
        self._ai_device_handler = AiDeviceHandler(self._daq_device_handler.get_ai_device(),
                                                  self._ai_params)

        # need to stop acquisition before scan
        if self._ai_device_handler.status == ul.ScanStatus.RUNNING:
            self._ai_device_handler.stop()

        self._ai_device_handler.scan()
        self._read_data_loop(do_save_data)
        
        if do_save_data:
            df = pd.DataFrame(pd.read_hdf(RAW_DATA_FILE_REL_PATH, key='dataset'))
            df = self._transform_ai_data(ai_channels, df)
            df.to_hdf(RAW_DATA_FILE_REL_PATH, key='dataset', format='table', mode='w')

        logging.info('EXPERIMENT_MANAGER: Continuous AI finished.')

    def ai_continuous_stop(self):
        self._ai_device_handler.stop()
        
    def _read_data_loop(self, do_save_data: bool):
        # if do_save_data: svae all in separate buffers (for finit ai/ao scan)
        # else: dump into dummy buffer file (for endless ai scan)
        try:
            tmp_ai_data = self._ai_device_handler.get_buffer()

            is_buffer_high_half = True
            half_buffer_len = int(len(tmp_ai_data) / 2)
            buffer_index = 0

            channels_num = self._ao_params.high_channel - self._ao_params.low_channel + 1
            if do_save_data:
                buffers_num = int(len(self._ao_buffer) / (self._ao_params.sample_rate * channels_num))
                logging.info('EXPERIMENT_MANAGER: Finite ai scan with data saving started.')
            else:
                buffers_num = 1 # just big number for quazi-infinite loop 
                # TODO: change later to separate thread process in order to be able stop the scan
                # with tango command
                logging.info('EXPERIMENT_MANAGER: Infinite ai scan with data overwriting started.')

            if not os.path.exists(RAW_DATA_FOLDER_REL_PATH):
                os.makedirs(RAW_DATA_FOLDER_REL_PATH)

            while True:
                try:
                    # Get AI operation status and index
                    ai_status, ai_transfer_status = self._ai_device_handler.status()
                    ai_index = ai_transfer_status.current_index

                    if buffer_index >= buffers_num:
                        self._ai_device_handler.stop()
                        if do_save_data:
                            # merging all the buffer files into one file raw_data.h5
                            fpath = RAW_DATA_FILE_REL_PATH
                            for i in list(range(buffers_num)):
                                buf_path = os.path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT.format(i))
                                df = pd.DataFrame(pd.read_hdf(buf_path, key='dataset'))
                                df.to_hdf(RAW_DATA_FILE_REL_PATH, key='dataset', format='table', append=True, mode='a')
                        break  

                    if ai_index > half_buffer_len and is_buffer_high_half and ai_status==1:
                        # reading low half 
                        df = pd.DataFrame(tmp_ai_data[:half_buffer_len])
                        if do_save_data:
                            logging.info('EXPERIMENT_MANAGER: Reading low half. Index = {}. Buffer index = {}'.format(ai_index, buffer_index))
                            fpath = os.path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT.format(buffer_index))
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
                        else:
                            logging.info('EXPERIMENT_MANAGER: read')
                            fpath = os.path.join(RAW_DATA_FOLDER_REL_PATH, BUFFER_DUMMY_1)
                            df.to_hdf(fpath, key='dataset', format='table', append=False, mode='a')
                        is_buffer_high_half = False
                    elif ai_index < half_buffer_len and not is_buffer_high_half and ai_status==1:
                        # reading high half
                        df = pd.DataFrame(tmp_ai_data[half_buffer_len:])
                        if do_save_data:
                            logging.info('EXPERIMENT_MANAGER: Reading high half. Index = {}. Buffer index = {}'.format(ai_index, buffer_index))
                            fpath = os.path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT.format(buffer_index))
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
                        else:
                            logging.info('EXPERIMENT_MANAGER: read')
                            fpath = os.path.join(RAW_DATA_FOLDER_REL_PATH, BUFFER_DUMMY_2)
                            df.to_hdf(fpath, key='dataset', format='table', append=False, mode='a')
                        is_buffer_high_half = True
                        buffer_index += 1
                except (ValueError, NameError, SyntaxError):
                    break

        except KeyboardInterrupt:
            logging.warning('EXPERIMENT_MANAGER: WARNING. Acquisition aborted.')
            pass



    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        if exc_value is not None:
            logging.error("EXPERIMENT_MANAGER: ERROR. Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))

        # if self._daq_device_handler:
        #     if self._ai_device_handler:
        #         if self._ai_device_handler.status() == ul.ScanStatus.RUNNING:
        #             self._ai_device_handler.stop()
        #         if self._ao_device_handler.status() == ul.ScanStatus.RUNNING:
        #             self._ao_device_handler.stop()
            # self._daq_device_handler.quit()
        # TODO: maybe add here dumping into h5 file??  # @EK: seems quite reasonable
