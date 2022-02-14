import uldaq as ul


class DaqDeviceHandler:
    def __init__(self, params: DaqParams):
        self._params = params

        devices = ul.get_daq_device_inventory(self._params.interface_type)
        devices_count = len(devices)
        if not devices_count:
            raise RuntimeError("Error. No DAQ devices found.")

        print("There are {} DAQ device(s) found:".format(devices_count))
        for i in range(devices_count):
            print("#{} : {} ({})".format(i, devices[i].product_name, devices[i].unique_id))

        descriptor_id = 0
        if devices_count > 1:
            input_str = "\nPlease select a DAQ device, enter a number between 0 and {} : ".format(devices_count - 1)
            descriptor_id = int(input(input_str))  # TODO: process bad input
            if descriptor_id not in range(devices_count):
                raise RuntimeError("Error. Invalid descriptor index entered.")
        self._daq_device = ul.DaqDevice(devices[descriptor_id])

    def connect(self):
        descriptor = self._daq_device.get_descriptor()
        print("Connecting to {} - please wait...".format(descriptor.dev_string))
        # For Ethernet devices using a connection_code other than the default
        # value of zero, change the line below to enter the desired code.
        self._daq_device.connect(connection_code=self._params.connection_code)

    def get(self):
        return self._daq_device

    def get_ai_device(self):
        return self._daq_device.get_ai_device()

    def get_ao_device(self):
        return self._daq_device.get_ao_device()

