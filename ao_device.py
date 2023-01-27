from typing import Tuple

import uldaq as ul
import logging


class AoParams:
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.scan_flags = ul.AOutScanFlag.DEFAULT  # 0
        self.options = ul.ScanOption.CONTINUOUS  # 8

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
        self._check_device()
        self._params = params

    def _check_device(self):
        if self._ao_device is None:
            error_str = "Error. DAQ device doesn't support analog output."
            logging.error(error_str)
            raise RuntimeError(error_str)

        info = self._ao_device.get_info()
        if not info.has_pacer():
            error_str = "Error. DAQ device doesn't support hardware paced analog output."
            logging.error(error_str)
            raise RuntimeError(error_str)

    def get(self) -> ul.AoDevice:
        """Provides explicit access to the uldaq.AoDevice."""
        return self._ao_device

    def stop(self):
        self._ao_device.scan_stop()

    def status(self) -> Tuple[ul.ScanStatus, ul.TransferStatus]:
        return self._ao_device.get_scan_status()

    # returns actual output scan rate
    def scan(self, ao_buffer) -> float:
        analog_range = ul.Range(self._params.range_id)
        samples_per_channel = int((len(ao_buffer) / (self._params.high_channel - self._params.low_channel + 1)))
        return self._ao_device.a_out_scan(self._params.low_channel, self._params.high_channel,
                                          analog_range, samples_per_channel,
                                          self._params.sample_rate, self._params.options, 
                                          self._params.scan_flags, ao_buffer)
    # set voltage profile to selected channel
    def iso_mode(self, ao_channel, voltage):
        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out(ao_channel, analog_range, self._params.scan_flags, voltage)
