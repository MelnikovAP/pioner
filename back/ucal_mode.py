from typing import List

from daq_device import DaqDeviceHandler
from settings import Settings
from calibration import Calibration


# TODO: should be abstract
class UcalMode:
    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: Settings,
                 calibration: Calibration,
                 ai_channels: List[int]):
        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._calibration = calibration
        self._ai_channels = ai_channels

    # TODO: pure virtual
    def arm(self):
        pass

    # TODO: pure virtual
    def is_armed(self) -> bool:
        pass

    # TODO: pure virtual
    def run(self):
        pass
