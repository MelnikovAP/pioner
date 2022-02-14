import uldaq as ul


class DaqParams:
    def __init__(self):
        self.interface_type = ul.InterfaceType.ANY
        self.connection_code = -1
