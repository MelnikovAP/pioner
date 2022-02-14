import uldaq as ul


class AiParams:
    def __init__(self):
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.input_mode = ul.AiInputMode.SINGLE_ENDED
        self.scan_flags = ul.AInScanFlag.DEFAULT
        self.status = ul.ScanStatus.IDLE
