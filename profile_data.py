import numpy as np

from enum import Enum


class DataType(Enum):
    ANY = "Any",
    TIME = "Time",
    TEMPERATURE = "Temperature",
    VOLTAGE = "Voltage"


class Profile1D:
    def __init__(self, type: DataType = DataType.ANY,
                 values: np.ndarray = np.array([])):
        self.__type = type
        self.__values = values

    def __repr__(self) -> str:
        return f"{self.__type.value[0]} values: {self.__values}"

    def __getitem__(self, index) -> float:
        return self.__values[index]

    def get_type(self) -> DataType:
        return self.__type

    def set_type(self, type: DataType):
        self.__type = type

    def get(self) -> np.ndarray:
        return self.__values.copy()

    def set(self, values: np.ndarray):
        self.__values = values

    def append(self, values: np.ndarray):
        self.__values = np.append(self.__values, values)

    def first(self) -> float:
        return self.__values[0]  # TODO: check

    def last(self) -> float:
        return self.__values[-1]  # TODO: check

    def size(self) -> int:
        return self.__values.size()

    def is_empty(self) -> bool:
        return not self.size()

    def is_valid(self) -> bool:
        return not self.is_empty()


class TimeProfile(Profile1D):
    def __init__(self, values: np.ndarray = np.array([])):
        super().__init__(type=DataType.TIME, values=values)


class TempProfile(Profile1D):
    def __init__(self, values: np.ndarray = np.array([])):
        super().__init__(type=DataType.TEMPERATURE, values=values)


class VoltageProfile(Profile1D):
    def __init__(self, values: np.ndarray = np.array([])):
        super().__init__(type=DataType.VOLTAGE, values=values)


class Profile2D:
    def __init__(self, x: Profile1D, y: Profile1D):
        self.x = x
        self.y = y

    def __repr__(self):
        return f"X: {self.x}\nY: {self.y}"

    def is_valid(self) -> bool:
        return self.x.is_valid() and \
               self.y.is_valid() and \
               self.x.size() == self.y.size()


class TempTimeProfile(Profile2D):
    def __init__(self):
        super().__init__(Profile1D(DataType.TIME),
                         Profile1D(DataType.TEMPERATURE))


class VoltageTimeProfile(Profile2D):
    def __init__(self):
        super().__init__(Profile1D(DataType.TIME),
                         Profile1D(DataType.VOLTAGE))


class VoltageTempProfile(Profile2D):
    def __init__(self):
        super().__init__(Profile1D(DataType.TEMPERATURE),
                         Profile1D(DataType.VOLTAGE))


if __name__ == "__main__":
    temp_time_profile = TempTimeProfile()
    temp_time_profile.x.set(np.array([1, 2, 3]))
    temp_time_profile.x.append(np.array([4, 5, 6]))
    print(temp_time_profile)
