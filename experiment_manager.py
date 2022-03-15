from daq_device_handler import DaqDeviceHandler
from ai_device_handler import AiDeviceHandler
from ao_device_handler import AoDeviceHandler
from acquisition_manager import AcquisitionManager
from ao_data_generator import AoDataGenerator

from scan_params import ScanParams
from daq_params import DaqParams
from ai_params import AiParams
from ao_params import AoParams

from time import sleep
import pandas as pd

import uldaq as ul
import sys


class ExperimentManager:
    def __init__(self, ao_data: AoDataGenerator, ai_channels: list,
                 scan_params: ScanParams, daq_params: DaqParams,
                 ai_params: AiParams, ao_params: AoParams):
        self._ao_data = ao_data
        self._ai_channels = ai_channels
        self._scan_params = scan_params
        self._daq_params = daq_params
        self._ai_params = ai_params
        self._ao_params = ao_params

        self.ai_data = {}
        for _i in self._ai_channels:
            self.ai_data[_i] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))

    def run(self):
        with AcquisitionManager(self._scan_params, self._daq_params,
                                self._ai_params, self._ao_params) as am:
            am.run()
            self.save_data_loop(am, self._ai_channels)

    def save_data_loop(self, am: AcquisitionManager, ai_channels: list):
        try:
            print("Enter 'CTRL+C' to terminate the process.\n")
            _dump_ai_data = am.ai_device_handler.data()

            _HIGH_HALF_FLAG = True
            _half_buffer_length = int(len(_dump_ai_data)/2)
            _step = am.ai_device_handler.channel_count

            while True:
                try:
                    # Get background operations statuses
                    ai_status, ai_transfer_status = am.ai_device_handler.status()
                    ao_status, ao_transfer_status = am.ao_device_handler.status()
                    if (ai_status != ul.ScanStatus.RUNNING) or (ao_status != ul.ScanStatus.RUNNING):
                        break
                    
                    _ai_index = ai_transfer_status.current_index
                    if _ai_index > _half_buffer_length and _HIGH_HALF_FLAG:
                        dump = pd.DataFrame(columns=self._ai_channels)
                        for _channel in self._ai_channels:
                            self.ai_data[_channel].extend(_dump_ai_data[:_half_buffer_length][_channel::_step])
                        _HIGH_HALF_FLAG = False
                        
                    elif _ai_index < _half_buffer_length and not _HIGH_HALF_FLAG:
                        dump = pd.DataFrame(columns=self._ai_channels)
                        for _channel in self._ai_channels:
                            self.ai_data[_channel].extend(_dump_ai_data[_half_buffer_length:][_channel::_step])
                        _HIGH_HALF_FLAG = True
                        
                    sleep(0.1)
                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            print('Acquisition aborted')
            pass



