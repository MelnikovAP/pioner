from scipy.interpolate import interp1d
import numpy as np

from segment_data import SegmentData, IsoSegment, RampSegment


def linear_interpolation(start_time: float, end_time: float, start_value: float,
                         end_value: float, sample_rate: int) -> np.ndarray:
    interpolation_function = interp1d(x=[start_time, end_time],
                                      y=[start_value, end_value], kind='linear')

    num_samples = int((end_time - start_time) * sample_rate)  # TODO: check
    time_samples = np.linspace(start_time, end_time, num_samples)
    return interpolation_function(time_samples)


# TODO: remove from here
def linear_segment_interpolation(segment: SegmentData, sample_rate: int) -> np.ndarray:
    if segment.is_linear():
        return linear_interpolation(segment.start_time, segment.end_time,
                                    segment.start_value, segment.end_value, sample_rate)
    else:
        raise ValueError("Invalid segment type for linear interpolation.")
