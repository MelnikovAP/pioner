import numpy as np


def sine_wave(amplitude: float, offset: float, pts_per_wave: int) -> np.ndarray:
    delta_x = 2 * np.pi / pts_per_wave
    x = np.array(range(pts_per_wave)) * delta_x

    return amplitude * np.sin(x) + offset


class SineGenerator:
    def __init__(self,
                 time_buffer: float,
                 sample_rate: int,
                 amplitude: float,
                 frequency: float,
                 offset: float):
        self._time_buffer = time_buffer
        self._sample_rate = sample_rate
        self._amplitude = amplitude
        self._frequency = frequency
        self._offset = offset

        self._check()

    def _check(self):
        # TODO: provide more accurate verification
        if self._time_buffer <= 0 \
                or self._sample_rate <= 0 \
                or self._amplitude <= 0 \
                or self._frequency <= 0 \
                or self._offset <= 0:
            raise ValueError()

    def get_single_wave(self):
        pts_per_wave = int(self._sample_rate / self._frequency)  # should be integer. TODO: check
        return sine_wave(self._amplitude, self._offset, pts_per_wave)

    def get(self) -> np.ndarray:
        single_wave = self.get_single_wave()

        result_wave = np.array([])

        waves_per_buffer = int(self._time_buffer * self._frequency)  # should be integer. TODO: check
        for i in range(waves_per_buffer):
            result_wave = np.concatenate([result_wave, single_wave])
        return result_wave
