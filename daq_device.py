import uldaq as ul
import logging


class DaqParams:
    def __init__(self):
        self.interface_type = ul.InterfaceType.ANY  # 7
        self.connection_code = -1

    def __str__(self):
        return str(vars(self))


class DaqDeviceHandler:
    def __init__(self, params: DaqParams):
        self._params = params
        self._init_daq_device()

    def _init_daq_device(self):
        devices = ul.get_daq_device_inventory(self._params.interface_type)
        if not devices:
            error_str = "Error. No DAQ devices found."
            logging.error(error_str)
            raise RuntimeError(error_str)

        # by default connecting only to the first DAQBoard with index 0
        self._daq_device = ul.DaqDevice(devices[0])

    def descriptor(self) -> ul.DaqDeviceDescriptor:
        return self._daq_device.get_descriptor()

    def is_connected(self):
        return self._daq_device.is_connected()

    def connect(self):
        descriptor = self.descriptor()
        logging.info("Connecting to {} - please wait...".format(descriptor.dev_string))
        # For Ethernet devices using a connection_code other than the default
        # value of zero, change the line below to enter the desired code.
        self._daq_device.connect(connection_code=self._params.connection_code)
        logging.info("DAQ device has been successfully connected.")

    def disconnect(self):
        logging.info("DAQ device has been disconnected.")
        return self._daq_device.disconnect()

    def release(self):
        logging.info("DAQ device has been released")
        return self._daq_device.release()

    def get(self) -> ul.DaqDevice:
        return self._daq_device

    def get_ai_device(self):
        return self._daq_device.get_ai_device()

    def get_ao_device(self):
        return self._daq_device.get_ao_device()
