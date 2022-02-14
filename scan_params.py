# import uldaq as ul


class ScanParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.channel_count = -1
        self.samples_per_channel = -1
        self.options = 8  # ul.ScanOption.CONTINUOUS
