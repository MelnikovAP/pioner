import uldaq as ul

class AoDataGenerator:
    # The buffer for AO device of daqboard should be linear.
    # This calss generates the linear buffer from dictionary, some kind of 2D array
    # like {'ch0': [.......], 'ch3': [........]}. Unused channels are being set to 0.

    def __init__(self, voltage_profiles: dict, low_channel: int, high_channel: int,
                    sample_rate: int):
        self._voltage_profiles = voltage_profiles
        self._low_channel = low_channel
        self._high_channel = high_channel
        self._sample_rate = sample_rate
        

        self._create_buffer()
        self._fill_buffer()

    def _create_buffer(self):
        self._channel_count = self._high_channel - self._low_channel + 1
        self.buffer = ul.create_float_buffer(self._channel_count, self._sample_rate)

    def _fill_buffer(self):
        _ch_list = list(range(self._channel_count))
        _ch_list = ['ch'+str(i) for i in _ch_list]
        print(_ch_list)
        print(list(self._voltage_profiles.keys()))
        print(self._voltage_profiles)
        # from numpy import linspace

        # start_volt = 0
        # end_volt = 1
        # volt_ramp = linspace(start_volt, end_volt, int(len(self.buffer)/4))
        # for i in range(len(volt_ramp)):
        #     self.buffer[i*4] = volt_ramp[i]
        #     self.buffer[i*4+1] = 0.5
        #     self.buffer[i*4+2] = 0.2
        #     self.buffer[i*4+3] = 0.3

        # import matplotlib.pyplot as plt
        # plt.plot(self.buffer[::4])
        # plt.plot(self.buffer[1::4])
        # plt.plot(self.buffer[2::4])
        # plt.plot(self.buffer[3::4])
        # plt.show()

    def __str__(self):
        return str(vars(self))



if __name__ == '__main__':
    try:
        voltage_profiles = {'ch0':[1,2,3,4,5,6,7,8,9],
                            'ch2':[21,22,23,24,25,26,27,28,29],
                            }
        ao_data_generator = AoDataGenerator(voltage_profiles, 0, 3, 1000)

    except BaseException as e:
        print(e)