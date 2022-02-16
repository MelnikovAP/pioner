# import uldaq as ul


class AiParams:
    def __init__(self):
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.input_mode = 2  # ul.AiInputMode.SINGLE_ENDED
        self.scan_flags = 0  # ul.AInScanFlag.DEFAULT

    def __str__(self):
        return str(vars(self))
