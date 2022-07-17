from daq_device import DaqDeviceHandler
from calibration import Calibration
from fastheat import FastHeat
from settings import SettingsParser
from constants import (CALIBRATION_PATH, DEFAULT_CALIBRATION_PATH, SETTINGS_PATH)


def main():
    # do read calibration
    calibration = Calibration()
    calibration.read(CALIBRATION_PATH)
    # calibration.read(DEFAULT_CALIBRATION_PATH)

    # do read settings
    settings_parser = SettingsParser(SETTINGS_PATH)

    # read temperature profile (from UI or from some experiment settings file)
    time_temp_table = {
        'time': [0, 100, 1000, 1500, 2000, 3000],
        'temperature': [0, 0, 1, 1, 0, 0]
    }

    # trying to connect to DaqDevice
    daq_params = settings_parser.get_daq_params()
    daq_device_handler = DaqDeviceHandler(daq_params)
    daq_device_handler.try_connect()

    with FastHeat(daq_device_handler, settings_parser,
                  time_temp_table, calibration) as fh:

        voltage_profiles = fh.arm()
        # for debug, remove later
        #     import matplotlib.pyplot as plt
        #     fig, ax1 = plt.subplots()
        #     ax1.plot(voltage_profiles[0])
        #     ax1.plot(voltage_profiles[1])
        #     plt.show()
        # ----------------------------------------

        fh.run()
        fh_data = fh.get_ai_data()
        # for debug, remove later
        #     import matplotlib.pyplot as plt
        #     fh_data.plot()
        #     plt.show()
        # ----------------------------------------


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        print(e)
