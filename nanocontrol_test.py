from daq_device import DaqDeviceHandler
from calibration import Calibration
from fastheat import FastMode
from settings import Settings
from constants import (CALIBRATION_PATH, DEFAULT_CALIBRATION_PATH, SETTINGS_PATH)
import matplotlib.pyplot as plt

def initial_setup():
    calibration = Calibration()
    calibration.read(DEFAULT_CALIBRATION_PATH)
    settings = Settings(SETTINGS_PATH)
    daq_device_handler = DaqDeviceHandler(settings.daq_params)
    print("DAQ settings: ", settings.daq_params)
    print("AI settings: ", settings.ai_params)
    print("AO settings: ", settings.ao_params)
    print("Calibration: ", calibration.comment)
    return calibration, settings, daq_device_handler

def connect(calibration, settings, daq_device_handler):
    daq_device_handler.try_connect()
    descriptor = daq_device_handler.get_descriptor()
    print("TANGO: Product info: {}".format(descriptor.dev_string))

def disconnect(daq_device_handler):
    daq_device_handler.disconnect()

def test_fast_heat(calibration, settings, daq_device_handler):
    time_temp_table = {
        'time': [0, 100, 1000, 1500, 2000, 3000],
        'temperature': [0, 0, 1, 1, 0, 0]
    }

    fh = FastMode(daq_device_handler, settings,
                  time_temp_table, calibration)
    voltage_profiles = fh.arm()
    print("LOG: Fast heating armed.")

    fig, ax1 = plt.subplots()
    ax1.plot(voltage_profiles['ch0'])
    ax1.plot(voltage_profiles['ch1'])
    plt.show()

    if fh.is_armed():
        print("LOG: Fast heating started.")
        fh.run()
        print("LOG: Fast heating finished.")


def main():
    # do read calibration
    calibration = Calibration()
    calibration.read(CALIBRATION_PATH)
    # calibration.read(DEFAULT_CALIBRATION_PATH)

    # do read settings
    settings = Settings(SETTINGS_PATH)

    # read temperature profile (from UI or from some experiment settings file)
    time_temp_table = {
        'time': [0, 100, 1000, 1500, 2000, 3000],
        'temperature': [0, 0, 1, 1, 0, 0]
    }

    # TODO: check maybe apply calibration right here ???

    # trying to connect to DaqDevice
    daq_params = settings.daq_params
    daq_device_handler = DaqDeviceHandler(daq_params)
    daq_device_handler.try_connect()

    with FastMode(daq_device_handler, settings,
                  time_temp_table, calibration) as fh:

        voltage_profiles = fh.arm()
        # for debug, remove later
        #     import matplotlib.pyplot as plt
        #     fig, ax1 = plt.subplots()
        #     ax1.plot(voltage_profiles['ch0'])
        #     ax1.plot(voltage_profiles['ch1'])
        #     plt.show()
        # ----------------------------------------

        fh.run()
        fh_data = fh.get_ai_data()
        print(fh_data)
        # for debug, remove later
        #     import matplotlib.pyplot as plt
        #     fh_data.plot()
        #     plt.show()
        # ----------------------------------------


if __name__ == '__main__':
    try:
        [calibration, settings, daq_device_handler] = initial_setup()
        connect(calibration, settings, daq_device_handler)
        test_fast_heat(calibration, settings, daq_device_handler)
        disconnect(daq_device_handler)
    except BaseException as e:
        print(e)
