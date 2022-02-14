from daq_device import DaqDeviceHandler
from ai_device import AiDeviceHandler
from ao_device import AoDeviceHandler


class AcquisitionManager:
    def __init__(self):
        daq_params = DaqParams()
        self._daq_device = DaqDeviceHandler(daq_params)
        self._ai_device = AiDeviceHandler(params, scan_params)
        self._ao_device = AoDeviceHandler(params, scan_params)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        if self._daq_device:
            if ai_status == ScanStatus.RUNNING:
                self._ai_device.scan_stop()
            if ao_status == ScanStatus.RUNNING:
                self._ao_device.scan_stop()
            if self._daq_device.is_connected():
                self._daq_device.disconnect()
            self._daq_device.release()

    def run(self):
        self._daq_device.connect()
        self._ai_device.scan()
        self._ao_device.scan()
