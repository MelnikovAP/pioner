from experiment_manager import ExperimentManager
from daq_device import DaqDeviceHandler
from utils import temperature_to_voltage
from settings import Settings
from calibration import Calibration
from constants import SETTINGS_PATH

import logging


class IsoMode:
    # receives chan_temp_volt as dict :
    # {"ch0": {"temp":float} }
    # voltage can be used instead of temperature ("volt" instead of "temp")
    # if "volt" - no calibration applied
    # if "temp" - calibration applied

    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: Settings,
                 calibration: Calibration,
                 chan_temp_volt: dict):
        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._calibration = calibration

        self._chan_temp_volt = chan_temp_volt

        self._channel = None
        self._voltage = None

    def arm(self) -> [int, float]:
        self._channel = int(list(self._chan_temp_volt.keys())[0].replace('ch', ''))
        key = list(list(self._chan_temp_volt.values())[0].keys())[0]
        self._voltage = float(list(list(self._chan_temp_volt.values())[0].values())[0])
        if key=='temp':
            self._voltage = float(temperature_to_voltage([self._voltage], self._calibration))
        return self._channel, self._voltage

    def is_armed(self) -> bool:
        return (self._channel is not None) and (self._voltage is not None)

    def run(self):
        with ExperimentManager(self._daq_device_handler,
                               self._settings) as em:
            em.ao_set(self._channel, self._voltage)


if __name__ == '__main__':

    settings = Settings(SETTINGS_PATH)
    chan_temp_volt = {'ch2':{'volt':0}}
    calibration = Calibration()

    daq_params = settings.daq_params
    daq_device_handler = DaqDeviceHandler(daq_params)
    daq_device_handler.try_connect()

    sm = IsoMode(daq_device_handler, settings, calibration, chan_temp_volt)
    sm.is_armed()
    sm.arm()
    sm.run()

    daq_device_handler.disconnect()