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

    def __str__(self):
        s = "Profile segment of type: {}\n"
        s += "start time: {}; end time: {}; duration: {}\n"
        s += "start value: {}; end value: {}\n"
        s.format(self.segment_type.name, self.start_time, self.end_time,
                 self.duration(), self.start_value, self.end_value)
        return s

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

    def __str__(self):
        return super().__str__()

    def style(self) -> SegmentStyle:
        return SegmentStyle.LINEAR


class RampSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 end_value: float):
        super().__init__(SegmentType.RAMP, start_time, end_time, start_value, end_value)

    def __str__(self):
        s = super().__str__()
        s += "rate: {}\n".format(self.rate())
        return s

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

    def __str__(self):
        s = super().__str__()
        s += "amplitude: {}; frequency: {}; offset: {}\n".format(self.amplitude, self.frequency, self.offset)
        return s

    def style(self) -> SegmentStyle:
        return SegmentStyle.PERIODIC


class SegmentFactory:
    @staticmethod
    def create_segment(segment_type,
                       start_time: float,
                       end_time: float,
                       start_value: float,
                       end_value: float):
        if segment_type == SegmentType.ISO:
            return IsoSegment(start_time, end_time, start_value)
        elif segment_type == SegmentType.RAMP:
            return RampSegment(start_time, end_time, start_value, end_value)
        elif segment_type == SegmentType.SINE:
            return SineSegment(start_time, end_time, start_value, end_value)
        else:
            raise ValueError("Invalid segment type")
