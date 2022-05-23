import uldaq as ul

class AiParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.input_mode = 2  # ul.AiInputMode.SINGLE_ENDED
        self.scan_flags = 0  # ul.AInScanFlag.DEFAULT
        self.options = 8  # ul.ScanOption.CONTINUOUS by default

    def __str__(self):
        return str(vars(self))

class AiDeviceHandler:
    """Wraps the analog-input uldaq.AiDevice."""

    def __init__(self, ai_device_from_daq: ul.AiDevice,
                 params: AiParams):
        """Initializes AI device and all parameters.

        Args:
            ai_device_from_daq: uldaq.AiDevice obtained from uldaq.DaqDevice.
            params: An AiParams instance, containing all needed analog-input parameters parsed from JSON.
        Raises:
            RuntimeError if the DAQ device doesn't support analog input or hardware paced analog input.
        """
        self._ai_device = ai_device_from_daq
        self._params = params

        if self._ai_device is None:
            raise RuntimeError("Error. DAQ device doesn't support analog input.")

        info = self._ai_device.get_info()
        if not info.has_pacer():
            raise RuntimeError("Error. DAQ device doesn't support hardware paced analog input.")

        if info.get_num_chans_by_mode(ul.AiInputMode.SINGLE_ENDED) <= 0:
            self._params.input_mode = ul.AiInputMode.DIFFERENTIAL

        self.channel_count = self._params.high_channel - self._params.low_channel + 1
        self._buffer = ul.create_float_buffer(self.channel_count, self._params.sample_rate)

    def get(self) -> ul.AiDevice:
        """Provides explicit access to the uldaq.AiDevice."""
        return self._ai_device                                   

    def data(self):
        return self._buffer

    def stop(self):
        self._ai_device.scan_stop()
  
    def status(self):
        return self._ai_device.get_scan_status()

    # returns actual input scan rate
    def scan(self) -> float:
        analog_range = ul.Range(self._params.range_id)
        return self._ai_device.a_in_scan(self._params.low_channel, self._params.high_channel, 
                                         self._params.input_mode, analog_range, 
                                         self._params.sample_rate,
                                         self._params.sample_rate, self._params.options, 
                                         self._params.scan_flags, self._buffer)