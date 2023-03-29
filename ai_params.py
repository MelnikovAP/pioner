from uldaq import AiInputMode, AInScanFlag, Range, ScanOption


class AiParams:
    def __init__(self):
        self.sample_rate: int = -1  # Hz

        self.low_channel: int = -1
        self.high_channel: int = -1

        self.range_id = Range.BIP10VOLTS  # 5
        self.input_mode = AiInputMode.SINGLE_ENDED  # 2
        self.scan_flags = AInScanFlag.DEFAULT  # 0
        self.options = ScanOption.CONTINUOUS  # 8

    def __str__(self):
        return str(vars(self))


if __name__ == "__main__":
    params = AiParams()
    print(params)
