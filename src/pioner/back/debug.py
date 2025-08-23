import sys
import numpy as np
from scipy import interpolate

import time

from pioner.shared import constants, settings, calibration, utils
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.fastheat import FastHeat

def debug_time_temp_table():
    time_temp_table = {
        'time': [0, 50, 450, 550, 950, 1000],
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

    cal = calibration.Calibration()
    cal.read('./calibration.json')
    # print(cal.safe_voltage, cal.max_temp, cal.min_temp)

    volt_program_points = utils.temperature_to_voltage(temp_program_points, cal)
    # print("voltage: \n{}".format(volt_program_points))

def debug_fast_heat():

    cal = calibration.Calibration()
    cal.read(constants.DEFAULT_CALIBRATION_FILE_REL_PATH)
    settings_obj = settings.BackSettings(constants.SETTINGS_FILE_REL_PATH)
    daq_device_handler = DaqDeviceHandler(settings_obj.daq_params)
    print("DAQ settings: ", settings_obj.daq_params)
    print("AI settings: ", settings_obj.ai_params)
    print("AO settings: ", settings_obj.ao_params)
    print("Calibration: ", cal.comment)
    
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

    fh = FastHeat(daq_device_handler, settings_obj,
                    time_temp_table, cal,
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
