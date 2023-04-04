from uldaq import AOutScanFlag, Range, ScanOption


class AoParams:
    def __init__(self):
        self.sample_rate: int = -1  # Hz
        self.time_buffer: float = -1  # seconds  # TODO: check maybe in integer number of milliseconds ?

        self.low_channel: int = -1
        self.high_channel: int = -1

        self.range_id = Range.BIP10VOLTS  # 5
        self.scan_flags = AOutScanFlag.DEFAULT  # 0
        self.options = ScanOption.DEFAULTIO  # 8

    def __str__(self):
        return str(vars(self))
