import uldaq as ul

class AoDataGenerator:
    def __init__(self, low_channel: int, high_channel: int, sample_rate: int):
        self._low_channel = low_channel
        self._high_channel = high_channel
        self._sample_rate = sample_rate

        self.create_buffer()
        self.fill_buffer()

    def create_buffer(self):
        self._channel_count = self._high_channel - self._low_channel + 1
        self.buffer = ul.create_float_buffer(self._channel_count, self._sample_rate)

    def fill_buffer(self):
        # not finished! should accept voltage profile for each channel
        from numpy import linspace

        start_volt = 0
        end_volt = 1
        volt_ramp = linspace(start_volt, end_volt, int(len(self.buffer)/4))
        for i in range(len(volt_ramp)):
            self.buffer[i*4] = volt_ramp[i]
            self.buffer[i*4+1] = 0.5
            self.buffer[i*4+2] = 0.2
            self.buffer[i*4+3] = 0.3

        # import matplotlib.pyplot as plt
        # plt.plot(self.buffer[::4])
        # plt.plot(self.buffer[1::4])
        # plt.plot(self.buffer[2::4])
        # plt.plot(self.buffer[3::4])
        # plt.show()

    def __str__(self):
        return str(vars(self))
