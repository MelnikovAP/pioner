from typing import List

from utils.segment_data import SegmentData
from utils.data_types import DataType


# for a single channel
class ProfileData:
    data_type: DataType
    segments: List[SegmentData]

    def __init__(self,
                 data_type: DataType,  # Y-axis: voltage or temperature
                 segments: List[SegmentData] = None):
        self.data_type = data_type
        if segments is None:
            segments = list()
        self.segments = segments

    def __str__(self):
        s = "Profile data of type: {}\n"
        s += "Segments:"
        for segment in self.segments:
            s += str(segment)
        return s
