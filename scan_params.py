# import uldaq as ul


class ScanParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.options = 8  # ul.ScanOption.CONTINUOUS by default
        
    def __str__(self):
        return str(vars(self))
