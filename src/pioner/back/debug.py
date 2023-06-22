import sys
from scipy import interpolate
import numpy as np
import matplotlib.pyplot as plt
import time

from shared.constants import *
from shared.settings import BackSettings
from shared.calibration import Calibration
from shared.utils import temperature_to_voltage
from back.daq_device import DaqDeviceHandler
from back.fastheat import FastHeat

def debug_time_temp_table():
    time_temp_table = {
        'time'.TIME: [0, 50, 450, 550, 950, 1000],
        'temperature': [0, 0, 5, 5, 0, 0]
    }

    # for not to truncate printing numpy arrays
    np.set_printoptions(threshold=sys.maxsize)

    time = time_temp_table['time']
    # print("time: \n{}".format(time))

    temp = time_temp_table['temperature']
    # print("temp: \n{}".format(temp))

    interpolation = interpolate.interp1d(x=time, y=temp, kind='linear')

    points_num = time[-1] + 1  # to get "time[-1]" intervals !!
    time_program_points = np.linspace(time[0], time[-1], points_num)
    # print("time upd: \n{}".format(time_program_points))

    temp_program_points = interpolation(time_program_points)
    # print("temp upd: \n{}".format(temp_program_points))

    calibration = Calibration()
    calibration.read('./calibration.json')
    # print(calibration.safe_voltage, calibration.max_temp, calibration.min_temp)

    volt_program_points = temperature_to_voltage(temp_program_points, calibration)
    # print("voltage: \n{}".format(volt_program_points))

def debug_fast_heat():

    calibration = Calibration()
    calibration.read(DEFAULT_CALIBRATION_FILE_REL_PATH)
    settings = BackSettings(SETTINGS_FILE_REL_PATH)
    daq_device_handler = DaqDeviceHandler(settings.daq_params)
    print("DAQ settings: ", settings.daq_params)
    print("AI settings: ", settings.ai_params)
    print("AO settings: ", settings.ao_params)
    print("Calibration: ", calibration.comment)
    
    daq_device_handler.try_connect()
    descriptor = daq_device_handler.get_descriptor()
    print("TANGO: Product info: {}".format(descriptor.dev_string))
    
    time_temp_table = {'ch0':{'time':[0, 3000], 
                                'temp':[0.1, 0.1]},
                        'ch1':{'time':[0, 100, 1100, 1900, 2900, 3000], 
                                'temp':[0, 0, 1, 1, 0, 0]},
                    }
    # fig, ax1 = plt.subplots()
    # ax1.plot(time_temp_table['ch1']['time'], time_temp_table['ch1']['temp'])
    # plt.show()

    fh = FastHeat(daq_device_handler, settings,
                    time_temp_table, calibration,
                    ai_channels = [0,1,3,4,5],
                    FAST_HEAT_CUSTOM_FLAG=False)
    print("LOG: Fast heating armed.")

    if fh.is_armed():
        print("LOG: Fast heating started.")
        t1 = time.time()
        fh.run()
        print("LOG: Fast heating finished. Took {} s.".format(time.time()-t1))

    daq_device_handler.disconnect()


if __name__ == "__main__":
    # debug_time_temp_table()
    debug_fast_heat()