from daq_device_handler import DaqDeviceHandler
from ai_device_handler import AiDeviceHandler
from ao_device_handler import AoDeviceHandler

from scan_params import ScanParams
from daq_params import DaqParams
from ai_params import AiParams
from ao_params import AoParams

from utils import reset_cursor, clear_eol
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
        self._ao_device_handler = AoDeviceHandler(self._daq_device_handler.get_ao_device(),
                                                  self._ao_params, self._scan_params)

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
        self._run_loop()

    def _run_loop(self):
        try:
            ai_data = self._ai_device_handler.data()

            while True:
                try:
                    reset_cursor()
                    # Get background operations statuses
                    ai_status, ai_transfer_status = self._ai_device_handler.status()
                    if ai_status != ul.ScanStatus.RUNNING:
                        break
                    ai_index = ai_transfer_status.current_index

                    ao_status, ao_transfer_status = self._ao_device_handler.status()
                    if ao_status != ul.ScanStatus.RUNNING:
                        break
                    ao_index = ao_transfer_status.current_index

                    # for debugging, remove later
                    print("Enter 'CTRL+C' to terminate the process.\n")

                    print("Scan rate = {:.6f} Hz\n".format(self._scan_params.sample_rate))

                    print("AI channels to read: from {} to {}".format(self._ai_params.low_channel,
                                                                      self._ai_params.high_channel))
                    print("AI currentTotalCount = {}\n".format(ai_transfer_status.current_total_count))
                    print("AI currentScanCount = {}\n".format(ai_transfer_status.current_scan_count))
                    print("AI currentIndex = {}\n".format(ai_index))

                    print("AO channels for output: from {} to {}\n".format(self._ao_params.low_channel,
                                                                           self._ao_params.high_channel))
                    print("AO currentTotalCount = {}\n".format(ao_transfer_status.current_total_count))
                    print("AO currentScanCount = {}\n".format(ao_transfer_status.current_scan_count))
                    print("AO currentIndex = {}\n".format(ao_index))
                    sys.stdout.flush()

                    # Display the data.
                    for i in range(self._scan_params.channel_count):
                        clear_eol()
                        print("channel = {}: {:.6f}".format(i + self._ai_params.low_channel,
                                                            ai_data[ai_index + i]))
                    sleep(0.1)

                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            import matplotlib.pyplot as plt
            
            # for debugging, remove later
            plt.plot(ai_data)
            plt.show()
            
            pass
