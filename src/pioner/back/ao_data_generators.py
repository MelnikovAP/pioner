import uldaq as ul

# TODO: add an interface class for different types of data generators


class PulseDataGenerator:
    # This class generates the buffer from dictionary, some kind of 2D array
    # like {'ch0': float, 'ch3': float}. Unused channels are being set to 0.
    # TODO: generate sin on reference channel
     
    def __init__(self, channel_voltages: dict, duration: int,
                 low_channel: int, high_channel: int):
        self._channel_voltages = channel_voltages
        self._low_channel = low_channel
        self._high_channel = high_channel
        self._channel_count = self._high_channel - self._low_channel + 1

        self._buffer_size = duration  # in points
        self._create_buffer()
        self._fill_buffer()

    def _create_buffer(self):
        self._buffer = ul.create_float_buffer(self._channel_count, self._buffer_size)

    def _fill_buffer(self):
        ch_list = list(range(self._low_channel, self._high_channel + 1))
        ch_list = ['ch' + str(i) for i in ch_list]

        for i in ch_list:
            if i not in list(self._channel_voltages.keys()):
                self._channel_voltages[i] = 0.
        
        print(self._channel_voltages['ch' + str(1)])
        for i in range(self._buffer_size):
            for ch in range(self._low_channel, self._high_channel + 1):
                self._buffer[i * self._channel_count + ch] = self._channel_voltages['ch' + str(ch)]

    def get_buffer(self) -> [float]:
        return self._buffer

    def __str__(self):
        return str(vars(self))


class ScanDataGenerator:
    # The buffer for AO device of daqboard should be linear.
    # This class generates the linear buffer from dictionary, some kind of 2D array
    # like {'ch0': [.......], 'ch3': [........]}. Unused channels are being set to 0.

    def __init__(self, voltage_profiles: dict,
                 low_channel: int, high_channel: int):
        self._voltage_profiles = voltage_profiles
        self._low_channel = low_channel
        self._high_channel = high_channel
        self._channel_count = self._high_channel - self._low_channel + 1
        self._buffer_size = len(list(self._voltage_profiles.items())[0][1])

        self._create_buffer()
        self._fill_buffer()

    def _create_buffer(self):
        self._buffer = ul.create_float_buffer(self._channel_count, self._buffer_size)

    def _fill_buffer(self):
        lens = list(map(len, self._voltage_profiles.values()))
        if len(set(lens)) > 1:
            raise ValueError("Cannot load analog output buffer. Channel profiles have different length.")

        lens_with_bf = lens.copy()
        lens_with_bf.append(self._buffer_size)
        if len(set(lens_with_bf)) > 1:
            raise ValueError("Cannot load analog output buffer. "
                             "One of the channel profile has length, different from buffer size.")
        ch_list = list(range(self._low_channel, self._high_channel + 1))
        ch_list = ['ch' + str(i) for i in ch_list]
        
        for i in ch_list:
            if i not in self._voltage_profiles.keys():
                self._voltage_profiles[i] = [0.] * self._buffer_size

        for i in range(self._buffer_size):
            for ch in range(self._low_channel, self._high_channel + 1):
                self._buffer[i * self._channel_count + ch] = self._voltage_profiles['ch' + str(ch)][i]

    def get_buffer(self) -> [float]:
        return self._buffer

    def __str__(self):
        return str(vars(self))


if __name__ == '__main__':
    try:
        from numpy import linspace

        local_voltage_profiles = {
            'ch0': 2,
            'ch2': 1
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
