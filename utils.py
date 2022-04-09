from typing import List


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


def voltage_to_temp(voltage, calibration):
    if voltage <= 0.:
        return 0.
    elif voltage >= calibration.safevoltage:
        return calibration.maxtemp
    else:
        return calibration.theater0*voltage + calibration.theater1*(voltage**2) + calibration.theater2*(voltage**3)


def temp_to_voltage(temp, calibration):
    if temp < calibration.mintemp:
        return 0.
    elif temp > calibration.maxtemp:
        return calibration.safevoltage
    else:
        return s#round(calibration.volt_temp_matrix['Volt'][calibration.volt_temp_matrix['Temp']>=temp].iloc[0], 3)
