from temp_volt_converters import temperature_to_voltage
from calibration import Calibration
from scipy import interpolate
import numpy as np
import sys


if __name__ == "__main__":

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

    calibration = Calibration()
    calibration.read('./calibration.json')
    # print(calibration.safe_voltage, calibration.max_temp, calibration.min_temp)

    volt_program_points = temperature_to_voltage(temp_program_points, calibration)
    # print("voltage: \n{}".format(volt_program_points))
