from experiment_manager import ExperimentManager
from daq_device import DaqDeviceHandler
from temp_volt_converters import temperature_to_voltage
from settings import Settings
from calibration import Calibration
from utils.constants import SETTINGS_PATH


class IsoMode:
    def __init__(self,
                 daq_device_handler: DaqDeviceHandler,
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
        if key == 'temp':
            self._voltage = float(temperature_to_voltage([self._voltage], self._calibration))
        return self._channel, self._voltage

    def is_armed(self) -> bool:
        return (self._channel is not None) and (self._voltage is not None)

    def run(self, do_ai:bool):
        with ExperimentManager(self._daq_device_handler,
                               self._settings) as self.em:
            self.em.ao_set(self._channel, self._voltage)
            if do_ai:
                self.em.ai_continuous([0,1,2,3,4,5], do_save_data=False)

    def ai_stop(self):
        self.em.ai_continuous_stop()


if __name__ == '__main__':

    _settings = Settings(SETTINGS_PATH)
    _chan_temp_volt = {'ch2': {'volt': 0}}
    _calibration = Calibration()

    daq_params = _settings.daq_params
    _daq_device_handler = DaqDeviceHandler(daq_params)
    _daq_device_handler.try_connect()

    sm = IsoMode(_daq_device_handler, _settings, _calibration, _chan_temp_volt)
    sm.is_armed()
    sm.arm()
    sm.run(do_ai=True)

    _daq_device_handler.disconnect()
