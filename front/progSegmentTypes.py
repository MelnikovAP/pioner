from enum import Enum
from typing import List


class SegmentType(Enum):
    NONE = 0,
    ISO = 1,
    RAMP = 2,
    SINE = 3


class SegmentData:
    def __init__(self,
                 segment_type: SegmentType,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 end_value: float):
        self.segment_type = segment_type
        self.start_time = start_time  # in seconds
        self.end_time = end_time  # in seconds
        self.start_value = start_value  # Volts or °C
        self.end_value = end_value  # Volts or °C

    def duration(self) -> float:
        return self.end_time - self.start_time


class IsoSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float):
        super().__init__(SegmentType.ISO, start_time, end_time, start_value, start_value)

    def __repr__(self):
        return f"IsoSegment({self.start_time}, {self.end_time}, {self.start_value})"


class RampSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 end_value: float):
        super().__init__(SegmentType.RAMP, start_time, end_time, start_value, end_value)

    def __repr__(self):
        return f"RampSegment({self.start_time}, {self.end_time}, {self.start_value}, {self.end_value})"

        # Volts or °C per second

    def rate(self) -> float:
        return (self.end_value - self.start_value) / self.duration()


class SineSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 amplitude: float,
                 frequency: float,
                 offset: float):
        super().__init__(SegmentType.SINE, start_time, end_time, start_value, start_value)

        self.amplitude = amplitude
        self.frequency = frequency
        self.offset = offset

    def __repr__(self):
        return f"SineSegment({self.start_time}, {self.end_time}, {self.start_value}, {self.end_value}, {self.amplitude}, {self.frequency}, {self.offset}  )"


class DataType(Enum):
    TIME = 1,
    TEMP = 2,
    VOLT = 3


class ProfileData:
    data_type: DataType
    segments: List[SegmentData]

    def __init__(self,
                 data_type: DataType,  # Y-axis
                 segments: List[SegmentData] = None):
        self.data_type = data_type
        if segments is None:
            segments = list()
        self.segments = segments

    def __str__(self):
        result = f"ProfileData(data_type={self.data_type}, segments=["
        for segment in self.segments:
            result += f"\n\t{segment}"
        result += "\n])"
        return result

    def __repr__(self):
        return f"ProfileData({self.data_type}, {self.segments})"