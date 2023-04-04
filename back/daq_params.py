from uldaq import InterfaceType


class DaqParams:
    def __init__(self):
        self.interface_type = InterfaceType.ANY
        self.connection_code = -1

    def __str__(self):
        return str(vars(self))
