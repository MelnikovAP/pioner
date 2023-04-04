from calibration import Calibration


class CalibrationProvider:
    def __init__(self,
                 calibration: Calibration,
                 sample_rate: int):
        self._calibration = calibration
        self._sample_rate = sample_rate
