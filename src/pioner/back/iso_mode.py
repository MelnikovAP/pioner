import logging

from pioner.shared.constants import *
from pioner.shared.settings import BackSettings
from pioner.shared.calibration import Calibration
from pioner.shared.utils import temperature_to_voltage
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.experiment_manager import ExperimentManager



class IsoMode:
    """Class to launch isothermal mode with predefined
    settings without saving AI data. The applied temperature / voltage 
    will be maintained util user sets it manually to 0 (could be done 
    with the same IsoMode methods) or disconnects DAQ device.
    
    Parameters
    ----------
        daq_device_handler : :obj:`pioner.daq_device.DaqDeviceHandler`
            DaqDeviceHandler class instance to handle connection 
            to DAQ device. Parameters of DAQ device should be preset
            from settings file while initializing of DaqDeviceHandler class instance
        
        settings : :obj:`pioner.shared.BackSettings`
            BackSettings class instance after parsing 
            of the configuration file with all 
            necessary acquisition parameters.
        
        calibration : :obj:`pioner.shared.calibration.Calibration`
            Calibration class instance, parsed from 
            :obj:`*.json` calibration file with 
            :obj:`pioner.shared.calibration.Calibration.read` method

        chan_temp_volt : :obj:`dict`
            Dictionary should have the following structure:
            :obj:`{"ch0": {"temp":[float]}},
            "ch1": {"volt":[float]},
            ...`. If "volt" is used, no calibration will be applied.
            If "temp" is used, calibration will be applied.
    """

    def __init__(self, daq_device_handler: DaqDeviceHandler,
                 settings: BackSettings,
                 chan_temp_volt: dict,
                 calibration: Calibration):
        self._daq_device_handler = daq_device_handler
        self._settings = settings
        self._chan_temp_volt = chan_temp_volt
        self._calibration = calibration

        self._channel = None
        self._voltage = None

    def arm(self) -> [int, float]:
        """
        Method to prepare isotherm. 
        Applies calibration coefficients to transform target temperature on heaters
        to voltage on AO channels.
        """
        self._channel = int(list(self._chan_temp_volt.keys())[0].replace('ch', ''))
        key = list(list(self._chan_temp_volt.values())[0].keys())[0]
        self._voltage = float(list(list(self._chan_temp_volt.values())[0].values())[0])
        if key=='temp':
            self._voltage = float(temperature_to_voltage([self._voltage], self._calibration))
        return self._channel, self._voltage

    def is_armed(self) -> bool:
        """
        Method to check if isothermal mode is prepared and voltage values are correct.

        Returns
        ---------
        :obj:`bool` 
            Returns :obj:`True` or :obj:`False` depending on state. 
        """
        return bool(self._channel is not None and self._voltage is not None)

    def run(self, do_ai:bool):
        """
        Method to start isotherm after preparation step (arming).
        Uses methods :obj:`pioner.back.experiment_manager.ExperimentManager.ao_set`
        and :obj:`pioner.back.experiment_manager.ExperimentManager.ai_continuous`
        to launch AO and AI scans. Does not save experimental data.
        """
        with ExperimentManager(self._daq_device_handler,
                               self._settings) as self.em:
            self.em.ao_set(self._channel, self._voltage)
            if do_ai:
                self.em.ai_continuous([0,1,2,3,4,5], do_save_data=False)

    def ai_stop(self):
        """
        Method to stop AI using method 
        :obj:`pioner.back.experiment_manager.ExperimentManager.ai_continuous_stop`
        """
        self.em.ai_continuous_stop()


if __name__ == '__main__':

    settings = BackSettings(SETTINGS_FILE_REL_PATH)
    chan_temp_volt = {'ch2':{'volt':0},
                        }
    calibration = Calibration()

    daq_params = settings.daq_params
    daq_device_handler = DaqDeviceHandler(daq_params)
    daq_device_handler.try_connect()

    sm = IsoMode(daq_device_handler, settings, chan_temp_volt, calibration)
    sm.is_armed()
    sm.arm()
    sm.run(do_ai=True)

    daq_device_handler.disconnect()