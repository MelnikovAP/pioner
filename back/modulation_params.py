class ModulationParams:
    def __init__(self):
        self.amplitude = 0.1
        self.frequency = 37.5
        self.offset = 0.1

    def __str__(self):
        return str(vars(self))
