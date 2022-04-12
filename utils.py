from typing import List
import pandas as pd
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


def voltage_to_temperature(voltage, calibration):
    volt = voltage.copy()
    volt[volt<0] = 0
    volt[volt>calibration.safevoltage] = calibration.safevoltage
    temp = calibration.theater0*volt + calibration.theater1*(volt**2) + calibration.theater2*(volt**3)
    return temp


def temperature_to_voltage(temp, calibration):
    # generating temp-volt dependency in full calibration range
    resolution = 0.001 # in V 
    volt_calib = np.linspace(0, calibration.safevoltage, int(1/resolution))
    v_test = pd.DataFrame({'Volt' : volt_calib})
    v_test['Temp'] = voltage_to_temperature(v_test['Volt'], calibration)

    
    temp = temp.copy()
    temp[temp<=calibration.mintemp] = calibration.mintemp
    temp[temp>=calibration.maxtemp] = calibration.maxtemp
    
    voltage = np.zeros(len(temp))
    for idx, t in np.ndenumerate(temp):
        voltage[idx] = v_test['Volt'][v_test['Temp']<=t].iloc[-1]
    
    return voltage

if __name__=='__main__':

    import numpy as np 
    import matplotlib.pyplot as plt
    from calibration import Calibration
    from time import time
    calibration = Calibration()

    temp_exp = np.linspace(0, 400, 1000)
    volt_exp = temperature_to_voltage(temp_exp, calibration)

    # plt.plot(temp_exp, label = 'temp_exp')
    # plt.plot(volt_exp, label = 'volt_exp')
    # plt.legend()
    # plt.show()