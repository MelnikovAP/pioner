from enum import Enum


class SegmentType(Enum):
    NONE = 0,
    ISO = 1,
    RAMP = 2,
    SINE = 3,
    # TRIANGLE = 4,
    # RECTANGLE = 5


class SegmentStyle(Enum):
    NONE = 0,
    LINEAR = 1,
    PERIODIC = 2


# TODO: make abstract
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

    def style(self) -> SegmentStyle:
        ...

    def duration(self) -> float:
        return self.end_time - self.start_time


class IsoSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float):
        super().__init__(SegmentType.ISO, start_time, end_time, start_value, start_value)

    def style(self) -> SegmentStyle:
        return SegmentStyle.LINEAR


class RampSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 end_value: float):
        super().__init__(SegmentType.RAMP, start_time, end_time, start_value, end_value)

    def style(self) -> SegmentStyle:
        return SegmentStyle.LINEAR


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
        # TODO: think about a final value
        super().__init__(SegmentType.SINE, start_time, end_time, start_value, start_value)

        self.amplitude = amplitude
        self.frequency = frequency
        self.offset = offset

    def style(self) -> SegmentStyle:
        return SegmentStyle.PERIODIC
