# import uldaq as ul


class DaqParams:
    def __init__(self):
        self.interface_type = 7  # ul.InterfaceType.ANY
        self.connection_code = -1

    def __str__(self):
        return str(vars(self))
