# import uldaq as ul


class AoParams:
    def __init__(self):
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.amplitude = 0
        self.offset = 0
        self.period = 0
        self.scan_flags = 0  # ul.AOutScanFlag.DEFAULT
