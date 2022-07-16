import numpy as np

from enum import Enum
# from typing import NamedTuple


class DataType(Enum):
    ANY = 0,
    TIME = 1,
    TEMPERATURE = 2,
    VOLTAGE = 3


def data_type_to_str(data_type: DataType):
    if data_type == DataType.TIME:
        return "Time"
    elif data_type == DataType.TEMPERATURE:
        return "Temperature"
    elif data_type == DataType.VOLTAGE:
        return "Voltage"
    else:
        return "Any"


class NamedData:
    def __init__(self, type: DataType = DataType.ANY,
                 values: np.ndarray = np.array([])):
        self.type = type
        self.values = values

    def __repr__(self):
        return f"{data_type_to_str(self.type)} values: {self.values}"


class ProfileData:
    def __init__(self, x_type: DataType,
                 y_type: DataType):
        self.__x = NamedData(type=x_type)
        self.__y = NamedData(type=y_type)

    def set_x(self, values: np.ndarray):
        self.__x.values = values

    def append_x(self, values: np.ndarray):
        self.__x.values = np.append(self.__x.values, values)

    def set_y(self, values: np.ndarray):
        self.__y.values = values

    def append_y(self, values: np.ndarray):
        self.__y.values = np.append(self.__y.values, values)

    def is_valid(self) -> bool:
        return len(self.__x.values) == len(self.__y.values)

    def __repr__(self):
        return f"X: {self.__x}.\nY: {self.__y}."


class TempTimeProfile(ProfileData):
    def __init__(self):
        super().__init__(DataType.TIME, DataType.TEMPERATURE)


class VoltageTimeProfile(ProfileData):
    def __init__(self):
        super().__init__(DataType.TIME, DataType.VOLTAGE)


class VoltageTempProfile(ProfileData):
    def __init__(self):
        super().__init__(DataType.TEMPERATURE, DataType.VOLTAGE)


if __name__ == "__main__":
    profile = TempTimeProfile()
    profile.set_x(np.array([1, 2, 3]))
    profile.append_x(np.array([1, 2, 3]))
    print(profile)
