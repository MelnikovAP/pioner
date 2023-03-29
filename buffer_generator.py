from sortedcontainers import SortedDict
from typing import Dict, List
from ctypes import Array

import numpy as np
import uldaq as ul
import math

from temp_volt_converters import temperature_to_voltage
from interpolation import linear_segment_interpolation
from segment_data import IsoSegment, RampSegment, SineSegment, SegmentStyle
from sine_generator import SineGenerator
from profile_data import ProfileData
from calibration import Calibration
from data_types import DataType
from settings import Settings


# TODO: check that channels start from 0 and what if not
# TODO: maybe add ChannelData = [int, ProfileData] ??

# output
# TODO: maybe create an actual Python generator (using a "yield" keyword) ??
class BufferGenerator:
    def __init__(self,
                 init_profiles_data: Dict[int, ProfileData],
                 calibration: Calibration,
                 settings: Settings,
                 chunk_duration: float):  # in seconds
        self._init_profiles_data = init_profiles_data
        self._calibration = calibration
        self._settings = settings

        self._chunk_duration = chunk_duration  # to divide initial profiles data into a list of profiles data chunks

        self._experiment_time = self._calc_experiment_time()
        self._chunks_count = math.ceil(self._experiment_time / self._chunk_duration)  # TODO: check, be careful
        self._profile_chunks = self._divide_profile_to_chunks()

        # self._create_buffer(channel_count, chan_buffer_size)
        # self._fill_buffer()

    # returns max channel duration, in seconds
    def _calc_experiment_time(self) -> float:
        max_duration = 0.
        for profile_data in self._init_profiles_data.values():
            duration = 0.
            for segment in profile_data.segments:
                duration += segment.duration()
            if duration > max_duration:
                max_duration = duration
        return max_duration

    # creates list of profiles for further chunk buffer generation
    def _divide_profile_to_chunks(self) -> List[Dict[int, ProfileData]]:
        profile_chunks: List[Dict[int, ProfileData]] = list()

        for chunk_num in range(self._chunks_count):  # starts from 0
            chunk_data: Dict[int, ProfileData] = dict()

            for channel, init_profile_data in self._init_profiles_data.items():
                chunk_profile_data = ProfileData(init_profile_data.data_type)

                init_segment = init_profile_data.segments[0]  # TODO: handle multiple segments, single - for now

                # init_segment_type = init_segment.segment_type
                init_start_time = init_segment.start_time
                init_end_time = init_segment.end_time
                init_start_value = init_segment.start_value
                # init_end_value = init_segment.end_value

                chunk_start_time = init_start_time + chunk_num * self._chunk_duration
                chunk_duration = min(self._chunk_duration, init_end_time - chunk_start_time)
                chunk_end_time = chunk_start_time + chunk_duration

                # TODO: create a factory
                if isinstance(init_segment, IsoSegment):
                    iso_segment = IsoSegment(chunk_start_time, chunk_end_time, init_start_value)
                    chunk_profile_data.segments.append(iso_segment)
                elif isinstance(init_segment, RampSegment):
                    rate = init_segment.rate()
                    chunk_start_value = init_start_value + chunk_num * self._chunk_duration * rate
                    chunk_end_value = chunk_start_value + chunk_duration * rate
                    ramp_segment = RampSegment(chunk_start_time, chunk_end_time, chunk_start_value, chunk_end_value)
                    chunk_profile_data.segments.append(ramp_segment)
                elif isinstance(init_segment, SineSegment):
                    sine_segment = SineSegment(chunk_start_time, chunk_end_time, init_start_value,
                                               init_segment.amplitude, init_segment.frequency, init_segment.offset)
                    chunk_profile_data.segments.append(sine_segment)
                else:
                    raise("Invalid segment type for channel {}".format(channel))

                chunk_data[channel] = chunk_profile_data

            profile_chunks.append(chunk_data)
        return profile_chunks

    # TODO: create a Python generator
    def _create_buffers(self) -> List[Array[float]]:
        sample_rate = self._settings.ao_params.sample_rate
        mod_params = self._settings.modulation_params

        buffers: List[Array[float]] = list()
        for profile_chunk in self._profile_chunks:
            chunk_interpolated_data_dict: Dict[int, np.ndarray] = SortedDict()  # TODO: check
            for channel, profile in profile_chunk.items():
                segment = profile.segments[0]  # TODO: consider more segments than one
                interpolated_data = np.array([])
                if segment.style() == SegmentStyle.LINEAR:
                    interpolated_data = linear_segment_interpolation(segment, sample_rate)
                elif isinstance(segment, SineSegment):
                    sine_generator = SineGenerator(segment.duration(), sample_rate,
                                                   mod_params.amplitude, mod_params.frequency, mod_params.offset)
                    interpolated_data = sine_generator.get()  # TODO: look into

                if profile.data_type == DataType.TEMP:
                    interpolated_data = temperature_to_voltage(interpolated_data, self._calibration)
                chunk_interpolated_data_dict[channel] = interpolated_data

            buffer = self._create_buffer(chunk_interpolated_data_dict)
            buffers.append(buffer)
        return buffers  # TODO: use "yield"

    def _create_buffer(self, channel_to_data_dict: Dict[int, np.ndarray]) -> Array[float]:
        channels_num = len(channel_to_data_dict)
        channel_buffer_size = len(channel_to_data_dict[0])  # since 0th channel should always be used !!!
        buffer = self._init_buffer(channels_num, channel_buffer_size)
        self._fill_buffer(buffer, channel_to_data_dict, channels_num, channel_buffer_size)
        return buffer

    @staticmethod
    def _init_buffer(channel_count: int, chan_buffer_size: int) -> Array[float]:
        return ul.create_float_buffer(channel_count, chan_buffer_size)

    @staticmethod
    def _fill_buffer(buffer: Array[float], channel_to_data_dict: Dict[int, np.ndarray],
                     channels_num: int, chan_buffer_size: int):
        for i in range(chan_buffer_size):
            for channel, data in channel_to_data_dict.items():
                buffer[i * channels_num + channel] = data[i]


# example of slow mode experiment
profiles_data = {
    0: ProfileData(
        DataType.VOLT,
        [
            SineSegment(0., 50., 0., 0.1, 37.5, 0.1)
        ]
    ),
    1: ProfileData(
        DataType.TEMP,
        [
            RampSegment(0., 50., 0., 100.),
        ]
    ),
    2: ProfileData(
        DataType.VOLT,
        [
            IsoSegment(0., 50., 0.)
        ]
    )
}


if __name__ == "__main__":
    pass
