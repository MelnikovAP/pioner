import uldaq as ul
import logging
import time


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
        devices = ul.get_daq_device_inventory(self._params.interface_type, 1)
        if not devices:
            error_str = "No DAQ devices found."
            logging.error("ERROR. {}".format(error_str))
            raise RuntimeError(error_str)

        # by default connecting only to the first DAQBoard with index 0
        self._daq_device = ul.DaqDevice(devices[0])

    def _is_device_ok(self) -> bool:
        return self._daq_device._handle is not None  # TODO: check a protected member usage

    def __del__(self):
        if self._is_device_ok():
            try:
                if self.is_connected():
                    self.disconnect()
            finally:
                self.release()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exe_type, exe_value, exe_traceback):
        self.disconnect()
        self.release()

    def get_descriptor(self) -> ul.DaqDeviceDescriptor:
        return self._daq_device.get_descriptor()

    def is_connected(self) -> bool:
        return self._daq_device.is_connected()

    def connect(self):
        descriptor = self.get_descriptor()
        logging.info("Connecting to {} - please wait...".format(descriptor.dev_string))
        # For Ethernet devices using a connection_code other than the default
        # value of zero, change the line below to enter the desired code.
        self._daq_device.connect(connection_code=self._params.connection_code)
        logging.info("DAQ device has been successfully connected.")

    def try_connect(self, timeout: int = 60, sleep_time: int = 2):
        for _ in range(timeout):
            if not self.is_connected():
                self.connect()
            time.sleep(sleep_time)
            if self.is_connected():
                return
        raise TimeoutError("Connection timed out.")

    def disconnect(self):
        self._daq_device.disconnect()
        logging.info("DAQ device has been disconnected.")

    def release(self):
        self._daq_device.release()
        logging.info("DAQ device has been released.")

    def reset(self):
        self._daq_device.reset()
        logging.info("DAQ device has been reset.")

    def quit(self):
        if self.is_connected():
            self.disconnect()
        self.release()

    def get(self) -> ul.DaqDevice:
        return self._daq_device

    def get_ai_device(self) -> ul.AiDevice:
        return self._daq_device.get_ai_device()

    def get_ao_device(self) -> ul.AoDevice:
        return self._daq_device.get_ao_device()
