from ctypes import Array
from typing import Dict

import uldaq as ul

from buffer_generator import BufferGenerator
from daq_device import DaqDeviceHandler
from ai_device import AiDeviceHandler
from ao_device import AoDeviceHandler
from calibration import Calibration
from profile_data import ProfileData
from settings import Settings


# TODO: think about hierarchy and inheritance
# TODO: use it to replace old ExperimentManager class
class NewExperimentManager:
    def __init__(self,
                 init_profiles_data: Dict[int, ProfileData],
                 daq_device_handler: DaqDeviceHandler,
                 calibration: Calibration,
                 settings: Settings):
        self._init_profiles_data = init_profiles_data

        self._calibration = calibration
        self._settings = settings

        self._ai_params = self._settings.ai_params
        self._ai_device_handler = AiDeviceHandler(daq_device_handler.get_ai_device(), self._ai_params)

        self._ao_params = self._settings.ao_params
        self._ao_device_handler = AoDeviceHandler(daq_device_handler.get_ao_device(), self._ao_params)

    # for modulation/iso modes only !!
    def ao_continuous(self):
        self._ao_params.options = ul.ScanOption.CONTINUOUS

        self._check_and_stop_ao_device()

        buffer_generator = BufferGenerator(self._init_profiles_data, self._calibration, self._settings)

        # only one buffer that should be repeated
        buffer = buffer_generator.get()

        self._ao_device_handler.iso_mode(ao_channel, voltage)

    def _check_and_stop_ao_device(self):
        if self._ao_device_handler.status == ul.ScanStatus.RUNNING:
            self._ao_device_handler.stop()

    def _check_and_stop_ai_device(self):
        if self._ai_device_handler.status == ul.ScanStatus.RUNNING:
            self._ai_device_handler.stop()
