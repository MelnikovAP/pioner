from constants import (RAW_DATA_FOLDER_REL_PATH, RAW_DATA_FILE_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT,
                       RAW_DATA_BUFFER_FILE_PREFIX)
from daq_device import DaqDeviceHandler
from ai_device import AiDeviceHandler
from ao_device import AoDeviceHandler
from ao_data_generators import ScanDataGenerator
from settings import Settings

from typing import List
from ctypes import Array
import pandas as pd
import uldaq as ul
import os
import glob
import logging

# TODO: check why we create analog devices inside scanning methods


class ExperimentManager:
    _ai_device_handler: AiDeviceHandler
    _ao_device_handler: AoDeviceHandler
    _ao_buffer: Array[float]

    def __init__(self,
                 daq_device_handler: DaqDeviceHandler,
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

    # TODO: think about it
    @staticmethod
    def get_ai_data() -> pd.DataFrame:
        df = pd.DataFrame(pd.read_hdf(RAW_DATA_FILE_REL_PATH, key='dataset'))
        return df

    def _transform_ai_data(self, ai_channels: List[int], df) -> pd.DataFrame:
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
        self._ao_params.options = ul.ScanOption.BLOCKIO  # 2  # TODO: check why not BURSTIO

        self._ao_buffer = ScanDataGenerator(voltage_profiles,
                                            self._ao_params.low_channel,
                                            self._ao_params.high_channel).get_buffer()

        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(),
                                                  self._ao_params)
        # need to stop AO before scan
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()

        self._ao_device_handler.scan(self._ao_buffer)

    # for setting voltage
    def ao_set(self, ao_channel, voltage):
        logging.info("EXPERIMENT_MANAGER: AO STATIC (SET) mode.\n")
        self._ao_params.options = ul.ScanOption.DEFAULTIO  # 0
        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(), self._ao_params)
        # need to stop AO before scan
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()
        
        self._ao_device_handler.iso_mode(ao_channel, voltage)

    # for modulation/iso modes only !!
    def ao_continuous(self):
        self._ao_params.options = ul.ScanOption.CONTINUOUS  # TODO: check
        # self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(), self._ao_params)

        # # need to stop AO before scan
        # if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
        #     self._ao_device_handler.stop()
        #
        # self._ao_buffer = ScanDataGenerator(voltage_profiles,
        #                                     self._ao_params.low_channel,
        #                                     self._ao_params.high_channel).get_buffer()
        #
        # self._ao_device_handler.iso_mode(ao_channel, voltage)

    def ai_continuous(self, ai_channels: List[int], do_save_data: bool):
        # AI buffer is 1 s and AI is made in loop. AO buffer equals to AO profile length.
        self._ai_params.options = ul.ScanOption.CONTINUOUS  # 8
        self._ai_device_handler = AiDeviceHandler(self._daq_device_handler.get_ai_device(),
                                                  self._ai_params)

        # need to stop acquisition before scan
        if self._ai_device_handler.status == ul.ScanStatus.RUNNING:
            self._ai_device_handler.stop()

        self._ai_device_handler.scan()
        self._read_data_loop(do_save_data)
        
        df = pd.DataFrame(pd.read_hdf(RAW_DATA_FILE_REL_PATH, key='dataset'))
        df = self._transform_ai_data(ai_channels, df)
        df.to_hdf(RAW_DATA_FILE_REL_PATH, key='dataset', format='table', mode='w')

        logging.info('EXPERIMENT_MANAGER: Continuous AI finished.')
        
    def _read_data_loop(self, do_save_data: bool):
        try:
            tmp_ai_data = self._ai_device_handler.get_buffer()

            is_buffer_high_half = True
            half_buffer_len = int(len(tmp_ai_data) / 2)
            buffer_index = 0

            channels_num = self._ao_params.high_channel - self._ao_params.low_channel + 1
            buffers_num = int(len(self._ao_buffer) / (self._ao_params.sample_rate * channels_num))

            if not os.path.exists(RAW_DATA_FOLDER_REL_PATH):
                os.makedirs(RAW_DATA_FOLDER_REL_PATH)

            while True:
                try:
                    # Get AI operation status and index
                    _, ai_transfer_status = self._ai_device_handler.status()
                    ai_index = ai_transfer_status.current_index

                    if buffer_index >= buffers_num:
                        self._ai_device_handler.stop()
                        # merging all the buffer files into one file raw_data.h5
                        # fpath = RAW_DATA_FILE_REL_PATH
                        for i in list(range(buffers_num)):
                            buf_path = os.path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT.format(i))
                            df = pd.DataFrame(pd.read_hdf(buf_path, key='dataset'))
                            df.to_hdf(RAW_DATA_FILE_REL_PATH, key='dataset', format='table', append=True, mode='a')
                        break  

                    if ai_index > half_buffer_len and is_buffer_high_half:
                        # reading low half 
                        logging.info('EXPERIMENT_MANAGER: Reading low half. Index = {}. Buffer index = {}'.format(ai_index, buffer_index))
                        df = pd.DataFrame(tmp_ai_data[:half_buffer_len])
                        if do_save_data:
                            fpath = os.path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT.format(buffer_index))
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
                        is_buffer_high_half = False
                    elif ai_index < half_buffer_len and not is_buffer_high_half:
                        # reading high half
                        logging.info('EXPERIMENT_MANAGER: Reading high half. Index = {}. Buffer index = {}'.format(ai_index, buffer_index))
                        df = pd.DataFrame(tmp_ai_data[half_buffer_len:])
                        if do_save_data:
                            fpath = os.path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_BUFFER_FILE_FORMAT.format(buffer_index))
                            df.to_hdf(fpath, key='dataset', format='table', append=True, mode='a')
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
