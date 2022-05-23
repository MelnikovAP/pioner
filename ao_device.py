import uldaq as ul

class AoParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.scan_flags = 0  # ul.AOutScanFlag.DEFAULT
        self.options = 8  # ul.ScanOption.CONTINUOUS by default

    def __str__(self):
        return str(vars(self))


class AoDeviceHandler:
    """Wraps the analog-output uldaq.AoDevice."""

    def __init__(self, ao_device_from_daq: ul.AoDevice,
                 params: AoParams):
        """Initializes AO device and all parameters.

        Args:
            ao_device_from_daq: uldaq.AoDevice obtained from uldaq.DaqDevice.
            params: An AoParams instance, containing all needed analog-output parameters parsed from JSON.
            
        Raises:
            RuntimeError if the DAQ device doesn't support analog output or hardware paced analog output.
        """
        self._ao_device = ao_device_from_daq
        self._params = params

        if self._ao_device is None:
            raise RuntimeError("Error. DAQ device doesn't support analog output.")

        info = self._ao_device.get_info()
        if not info.has_pacer():
            raise RuntimeError("Error. DAQ device doesn't support hardware paced analog output.")

    def get(self) -> ul.AoDevice:
        """Provides explicit access to the uldaq.AoDevice."""
        return self._ao_device

    def stop(self):
        self._ao_device.scan_stop()

    def status(self):
        return self._ao_device.get_scan_status()

    # returns actual output scan rate
    def scan(self, ao_buffer) -> float:
        return self._ao_device.a_out_scan(self._params.low_channel, self._params.high_channel,
                                          ul.Range(self._params.range_id), 
                                          self._params.sample_rate,
                                          self._params.sample_rate, self._params.options, 
                                          self._params.scan_flags, ao_buffer)