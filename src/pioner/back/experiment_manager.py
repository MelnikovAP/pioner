import glob
import logging
import os
from typing import List
import pandas as pd
import uldaq as ul

from pioner.shared.constants import *
from pioner.shared.settings import BackSettings
from pioner.back.ai_device import AiDeviceHandler
from pioner.back.ao_data_generators import ScanDataGenerator
from pioner.back.ao_device import AoDeviceHandler
from pioner.back.daq_device import DaqDeviceHandler

# TODO: check why we create analog devices inside scanning methods


class ExperimentManager:
    """Class to control experiment, manage AO/AI and buffer handle.
    
    Parameters
    ----------
        daq_device_handler : :obj:`pioner.daq_device.DaqDeviceHandler`
            DaqDeviceHandler class instance to handle connection 
            to DAQ device. Parameters of DAQ device should be preset
            from settings file while initializing of DaqDeviceHandler class instance
        
        settings : :obj:`pioner.shared.BackSettings`
            BackSettings class instance after parsing 
            of the configuration file with all 
            necessary acquisition parameters.
    """

    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: BackSettings):
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
        """Reads raw buffer from :obj:`*.hdf` file. Note: Pandas
        library is used to read / write datasets.
        Array in file is already transformed from 1D to 2D array. 
        
        Returns
        ------- 
            :obj:`pd.DataFrame` 
                Returns Pandas array: :obj:`['channel #':[float] ... 'channel #':[float]]`
                
        """
                
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
        """Method to launch AO scan with predefined voltage profiles on channels. 
        Makes AO buffer using :obj:`pioner.back.ao_data_generators.ScanDataGenerator` 
        and AoDeviceHandler instance using pared settings. To launch the scan uses 
        :obj:`pioner.back.ao_device.AoDeviceHandler.scan`
        
        Args
        ----------
            voltage_profiles : :obj:`dict`
                Dictionary should have the following format: 
                :obj:`{'ch0': [float], 'ch3': [float]}`. 
                
        """
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
        """Method to set and hold voltage on selected AO channel, uses 
        :obj:`pioner.back.ao_device.AoDeviceHandler.iso_mode`
        
        Note
        ----
            The voltage remains on the channel until DAQ board released and disconnected.
        
        Args
        ----------
            ao_channel : :obj:`int`
                AO channel number (usually from 0 to 3).

            voltage : :obj:`float`
                Voltage value, usually from 0 to 10.
                
        """
                
        logging.info("EXPERIMENT_MANAGER: AO STATIC (SET) mode.\n")
        self._ao_params.options = ul.ScanOption.DEFAULTIO  # 0
        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(),
                                                  self._ao_params)
        # # need to stop AO before scan
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()
        
        self._ao_device_handler.iso_mode(ao_channel, voltage)


    def ai_continuous(self, ai_channels: List[int], do_save_data: bool):
        """Method to launch AI in continuous scan mode. 
        Reading is made with circular buffer, divided into two halves.
        Buffer length = 1 s. The first 0.5 s data points (low half buffer) 
        are being read while new data points are being recorded to the 
        second 0.5 s buffer (high half buffer). Contrary, when writing 
        points to the first 0.5 s cycle buffer (low half buffer), data 
        is read from the second part of the buffer (high half buffer). 
        Uses :obj:`pioner.back.ai_device.AiDeviceHandler.scan` to start 
        acquisition.
        
        Args
        ----------
            ai_channels : :obj:`List[int]`
                AI channels list to read (usually from 0 to 15).

            do_save_data : :obj:`bool`
                if :obj:`True`, saves all the data to separate :obj:`*.hdf` files. 
                Used for fast finite AI/AO scans.
                If :obj:`False`, saves all the data to one :obj:`*.hdf` file,
                continuously overwriting data. Used for long or infinite AI/AO scans.
                Data can be accessed later using 
                :obj:`pioner.back.experiment_manager.get_ai_data` method. 
                
        """
        
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
        """Method to stop AI during continuous scan, using 
        :obj:`pioner.back.ai_device.AiDeviceHandler.stop`.
        """
        self._ai_device_handler.stop()
        
    def _read_data_loop(self, do_save_data: bool):
        # if do_save_data: save all in separate buffers (for finite ai/ao scan)
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
                buffers_num = 1 # just a big number for quasi-infinite loop
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
