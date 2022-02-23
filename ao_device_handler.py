from scan_params import ScanParams
from ao_params import AoParams

import uldaq as ul


class AoDeviceHandler:
    """Wraps the analog-output uldaq.AoDevice."""

    def __init__(self, ao_device_from_daq: ul.AoDevice,
                 params: AoParams, scan_params: ScanParams):
        """Initializes AO device and all parameters.

        Args:
            ao_device_from_daq: uldaq.AoDevice obtained from uldaq.DaqDevice.
            params: An AoParams instance, containing all needed analog-output parameters parsed from JSON.
            scan_params: A ScanParams instance, containing all needed scanning parameters parsed from JSON.

        Raises:
            RuntimeError if the DAQ device doesn't support analog output or hardware paced analog output.
        """
        self._ao_device = ao_device_from_daq
        self._params = params
        self._scan_params = scan_params

        if self._ao_device is None:
            raise RuntimeError("Error. DAQ device doesn't support analog output.")

        info = self._ao_device.get_info()
        if not info.has_pacer():
            raise RuntimeError("Error. DAQ device doesn't support hardware paced analog output.")

        channel_count = self._params.high_channel - self._params.low_channel + 1
        self._buffer = ul.create_float_buffer(channel_count, self._scan_params.sample_rate)
        self._fill_buffer()

    def get(self) -> ul.AoDevice:
        """Provides explicit access to the uldaq.AoDevice."""
        return self._ao_device

    # returns actual output scan rate
    def scan(self) -> float:
        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out_scan(self._params.low_channel, self._params.high_channel,
                                          analog_range, self._scan_params.sample_rate,
                                          self._scan_params.sample_rate, self._scan_params.options, 
                                          self._params.scan_flags, self._buffer)

    def stop(self):
        self._ao_device.scan_stop()

    def status(self):
        return self._ao_device.get_scan_status()

    # here we have to add another class with voltage profile parameters
    # below 4 channels are used
    def _fill_buffer(self):
        from numpy import linspace

        start_volt = 0
        end_volt = 1
        volt_ramp = linspace(start_volt, end_volt, int(len(self._buffer)/4))
        for i in range(len(volt_ramp)):
            self._buffer[i*4] = volt_ramp[i]
            self._buffer[i*4+1] = 0.1
            self._buffer[i*4+2] = 0.2
            self._buffer[i*4+3] = 0.3

        import matplotlib.pyplot as plt
        plt.plot(self._buffer[::4])
        plt.plot(self._buffer[1::4])
        plt.plot(self._buffer[2::4])
        plt.plot(self._buffer[3::4])
        plt.show()
