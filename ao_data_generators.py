from ctypes import Array
from typing import Dict

import numpy as np
import uldaq as ul

from profile_data import VoltageProfile


class PulseDataGenerator:
    # This class generates the buffer from dictionary, some kind of 2D array
    # like {0: float, 3: float}. Unused channels are being set to 0.
    # TODO: generate sin on reference channel
     
    def __init__(self, channel_voltages: dict, duration: int,
                 low_channel: int, high_channel: int):
        self._channel_voltages = channel_voltages
        self._low_channel = low_channel
        self._high_channel = high_channel
        self._buffer_size = duration  # in points
        self._init_and_fill_buffer()

    def _init_and_fill_buffer(self):
        channel_count = self._high_channel - self._low_channel + 1
        self._buffer = ul.create_float_buffer(channel_count, self._buffer_size)

        for i in range(self._low_channel, self._high_channel + 1):
            if i not in list(self._channel_voltages.keys()):
                self._channel_voltages[i] = 0.

        # TODO: check how it works if low_channel > 0
        for i in range(self._buffer_size):
            for j in range(0, channel_count):
                self._buffer[i * channel_count + j] = self._channel_voltages[self._low_channel + j]

    def get_buffer(self) -> Array[float]:
        return self._buffer

    def __str__(self):
        return str(vars(self))


class ScanDataGenerator:
    # The buffer for AO device of daqboard should be linear.
    # This class generates the linear buffer from dictionary, some kind of 2D array
    # like {0: [.......], 3: [........]}. Unused channels are being set to 0.

    def __init__(self, voltage_profiles: Dict[int, VoltageProfile],
                 low_channel: int, high_channel: int):
        self._voltage_profiles = voltage_profiles
        self._low_channel = low_channel
        self._high_channel = high_channel
        self._init_and_fill_buffer()

    def _init_and_fill_buffer(self):
        profile_sizes = set()
        for profile in self._voltage_profiles.values():
            profile_sizes.add(profile.size())

        if len(profile_sizes) > 1:
            raise ValueError("Cannot load analog output buffer. Channel profiles have different length.")
        buffer_size = list(profile_sizes)[0]

        for i in range(self._low_channel, self._high_channel + 1):
            if i not in self._voltage_profiles.keys():
                self._voltage_profiles[i] = VoltageProfile(np.array([0.] * buffer_size))

        channel_count = (self._high_channel - self._low_channel + 1)
        self._buffer = ul.create_float_buffer(channel_count, buffer_size)

        # TODO: check how it works if low_channel > 0
        for i in range(buffer_size):
            for j in range(0, channel_count):
                self._buffer[i * channel_count + j] = self._voltage_profiles[self._low_channel + j][i]

    def get_buffer(self) -> Array[float]:
        return self._buffer

    def __str__(self):
        return str(vars(self))


if __name__ == '__main__':
    try:
        from numpy import linspace

        local_voltage_profiles = {
            0: 2,
            2: 1
        }
        ao_data_generator = PulseDataGenerator(local_voltage_profiles, 100, 0, 3)
        buffer = ao_data_generator.get_buffer()

        import matplotlib.pyplot as plt
        plt.plot(buffer[::4])
        plt.plot(buffer[1::4])
        plt.plot(buffer[2::4])
        plt.plot(buffer[3::4])
        plt.show()

    except BaseException as e:
        print(e)
