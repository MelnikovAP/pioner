from typing import List

from ucal_mode import UcalMode
from daq_device import DaqDeviceHandler
from settings import Settings
from calibration import Calibration


class ModulationMode(UcalMode):
    def __init__(self,
                 daq_device_handler: DaqDeviceHandler,
                 settings: Settings,
                 calibration: Calibration,
                 ai_channels: List[int]):
        super().__init__(daq_device_handler, settings, calibration, ai_channels)

        self._params = settings.modulation_params

    def arm(self) -> [int, float]:
        chan = 0  # TODO: think from where to get

        # self._params

        self._voltage = float(temperature_to_voltage([self._voltage], self._calibration))
        return self._channel, self._voltage

    def is_armed(self) -> bool:
        return True

    def run(self):
        with ExperimentManager(self._daq_device_handler,
                               self._settings) as em:
            em.ao_set(self._channel, self._voltage)
