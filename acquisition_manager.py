from daq_device_handler import DaqDeviceHandler
from ai_device_handler import AiDeviceHandler
from ao_device_handler import AoDeviceHandler

from scan_params import ScanParams
from daq_params import DaqParams
from ai_params import AiParams
from ao_params import AoParams

from time import sleep

import uldaq as ul


class AcquisitionManager:
    def __init__(self, scan_params: ScanParams, daq_params: DaqParams,
                 ai_params: AiParams, ao_params: AoParams):
        self._scan_params = scan_params
        self._daq_params = daq_params
        self._ai_params = ai_params
        self._ao_params = ao_params

        self._daq_device_handler = DaqDeviceHandler(self._daq_params)
        self.ai_device_handler = AiDeviceHandler(self._daq_device_handler.get_ai_device(),
                                                  self._ai_params, self._scan_params)

        self._common_ao_device = self._daq_device_handler.get_ao_device()
        self.ao_device_handler = AoDeviceHandler(self._common_ao_device,
                                                  self._ao_params, self._scan_params)


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Exception {} of type {}. Traceback: {}".format(exc_value, exc_type, exc_tb))
        if self._daq_device_handler:
            if self.ai_device_handler.status() == ul.ScanStatus.RUNNING:
                self.ai_device_handler.stop()
            if self.ao_device_handler.status() == ul.ScanStatus.RUNNING:
                self.ao_device_handler.stop()
            if self._daq_device_handler.is_connected():
                self._daq_device_handler.disconnect()
            self._daq_device_handler.release()

    def run(self):
        self._daq_device_handler.connect()
        self.ai_device_handler.scan()
        self.ao_device_handler.scan()
