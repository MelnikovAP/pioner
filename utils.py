from calibration import Calibration

from typing import List
from bisect import bisect_left
import numpy as np


def is_int(key) -> bool:
    if isinstance(key, int) or isinstance(key, str) and key.isdigit():
        return True


def is_int_or_raise(key) -> bool:
    if is_int(key):
        return True
    raise ValueError("'{}' is not an integer value.".format(key))


def list_bitwise_or(ints: List[int]) -> int:
    res = 0
    for i in ints:
        res |= i
    return res

# calorimeter utils
# ====================================================
def voltage_to_temperature(voltage: np.ndarray, calibration: Calibration) -> np.ndarray:
    volt = voltage.copy()
    volt[volt < 0] = 0
    volt[volt > calibration.safe_voltage] = calibration.safe_voltage
    temp = calibration.theater0 * volt + calibration.theater1 * (volt**2) + calibration.theater2 * (volt**3)
    return temp


# TODO: think maybe to create a T-V (and vice versa) converter class
def temperature_to_voltage(temp: np.ndarray, calibration:  Calibration) -> np.ndarray:
    # generating temp-volt dependency in full calibration range
    resolution = 0.0001  # V
    volt_calib = np.linspace(0, calibration.safe_voltage, int(1 / resolution))

    temp_calib = voltage_to_temperature(volt_calib, calibration)
    temp_calib[temp_calib <= calibration.min_temp] = calibration.min_temp
    temp_calib[temp_calib >= calibration.max_temp] = calibration.max_temp

    voltage = np.zeros(len(temp))
    for i, t in np.ndenumerate(temp):
        idx = bisect_left(temp_calib, t)
        voltage[i] = volt_calib[idx]

    return voltage.round(4)


if __name__ == '__main__':

    # import matplotlib.pyplot as plt
    from time import time

    temp_exp_1 = np.zeros(1000) - 1
    temp_exp_2 = np.linspace(-1, 300, 3000)
    temp_exp_3 = np.ones(1000) + 299
    temp_exp_4 = np.linspace(300, -2, 3000)
    temp_exp_5 = np.zeros(1000) - 2
    temp_exp = np.concatenate((temp_exp_1, temp_exp_2, temp_exp_3, temp_exp_4, temp_exp_5))
    # plt.plot(temp_exp)
    # plt.show()

    t1 = time()
    volt_exp = temperature_to_voltage(temp_exp, Calibration())
    t2 = time()
    print(t2 - t1)
    print(volt_exp[1000:1100])
    # plt.plot(temp_exp, label = 'temp_exp')
    # plt.plot(volt_exp, label = 'volt_exp')
    # plt.legend()
    # plt.show()