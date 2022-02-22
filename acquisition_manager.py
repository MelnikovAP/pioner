from daq_device_handler import DaqDeviceHandler
from ai_device_handler import AiDeviceHandler
from ao_device_handler import AoDeviceHandler

from scan_params import ScanParams
from daq_params import DaqParams
from ai_params import AiParams
from ao_params import AoParams

from time import sleep

import uldaq as ul
import sys


class AcquisitionManager:
    def __init__(self, scan_params: ScanParams, daq_params: DaqParams,
                 ai_params: AiParams, ao_params: AoParams):
        self._scan_params = scan_params
        self._daq_params = daq_params
        self._ai_params = ai_params
        self._ao_params = ao_params

        self._daq_device_handler = DaqDeviceHandler(self._daq_params)
        self._ai_device_handler = AiDeviceHandler(self._daq_device_handler.get_ai_device(),
                                                  self._ai_params, self._scan_params)

        self._common_ao_device = self._daq_device_handler.get_ao_device()
        self._ao_device_handler = AoDeviceHandler(self._common_ao_device,
                                                  self._ao_params, self._scan_params)

        self.ai_data = []

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

    def run(self):
        self._daq_device_handler.connect()
        self._ai_device_handler.scan()
        self._ao_device_handler.scan()
        self._save_data_loop()

    def _save_data_loop(self):
        try:
            print("Enter 'CTRL+C' to terminate the process.\n")
            dump_ai_data = self._ai_device_handler.data()

            _HIGH_HALF_FLAG = True
            _half_buffer_lenght = int(len(dump_ai_data)/2)

            while True:
                try:
                    # Get background operations statuses
                    ai_status, ai_transfer_status = self._ai_device_handler.status()
                    ao_status, ao_transfer_status = self._ao_device_handler.status()
                    if (ai_status != ul.ScanStatus.RUNNING) or (ao_status != ul.ScanStatus.RUNNING):
                        break

                    ai_index = ai_transfer_status.current_index
                    if ai_index>_half_buffer_lenght and _HIGH_HALF_FLAG:
                        self.ai_data.extend(dump_ai_data[:_half_buffer_lenght])
                        _HIGH_HALF_FLAG = False
                    elif ai_index<_half_buffer_lenght and not _HIGH_HALF_FLAG:
                        self.ai_data.extend(dump_ai_data[_half_buffer_lenght:])
                        _HIGH_HALF_FLAG = True

                    sleep(0.1)
                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:

            print('Acquisition aborted. Plotting the data...')
            pass
        finally:
            
            # here we have to add another class with voltage read
            # below 10 channels are used
            import matplotlib.pyplot as plt
            fig, ax1 = plt.subplots()
            ax2 = ax1.twinx()
            for i in range(1,10):
                ax1.plot(self.ai_data[i::10], label='channel #'+str(i) )
            ax2.plot(self.ai_data[0::10], label='channel #0')
            ax1.legend()
            ax2.legend()
            plt.show()
