import uldaq as ul


class ScanParams:
    def __init__(self):
        self.sample_rate = 0  # Hz
        self.channel_count = 2
        self.samples_per_channel = self.channel_count * self.sample_rate
        self.options = ul.ScanOption.CONTINUOUS
