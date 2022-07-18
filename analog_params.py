import uldaq as ul


class AiParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.input_mode = ul.AiInputMode.SINGLE_ENDED  # 2
        self.scan_flags = ul.AInScanFlag.DEFAULT  # 0
        self.options = ul.ScanOption.CONTINUOUS  # 8

    def __str__(self):
        return str(vars(self))


class AoParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.scan_flags = ul.AOutScanFlag.DEFAULT  # 0
        self.options = ul.ScanOption.CONTINUOUS  # 8

    def __str__(self):
        return str(vars(self))
