import logging
from typing import Tuple
from ctypes import Array
import uldaq as ul


class AoParams:
    """General class to represent main AO DAQ parameters. 
    Deafult paramteres cannot be used to initialize uldaq.AoDevice,
    they need to be parsed from file or specified manually.
    
    Args:
        sample_rate (:obj:`int`): description.
        range_id (:obj:`int`): description.
        low_channel (:obj:`int`): description.
        high_channel (:obj:`int`): description.
        scan_flags (:obj:`int`): ul.AOutScanFlag description.
        options (:obj:`int`): ul.ScanOption description.
        
    """
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
    """Wraps the analog output uldaq.AoDevice.
    Initializes AO DAQ device and all parameters.

    Args:
        ao_device_from_daq (:obj:`ul.AoDevice`): uldaq.AoDevice obtained from uldaq.DaqDevice.
        params (:obj:`AoParams`): An AoParams instance, containing all needed analog-output parameters parsed from JSON.
        
    Raises:
        RuntimeError if the DAQ device doesn't support analog output or hardware paced analog output.
    """

    def __init__(self, ao_device_from_daq: ul.AoDevice,
                 params: AoParams):
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
        """Interrupts analog output scan"""
        self._ao_device.scan_stop()

    def status(self) -> Tuple[ul.ScanStatus, ul.TransferStatus]:
        """Provides analog output scan and data transfer status"""
        return self._ao_device.get_scan_status()

    def scan(self, ao_buffer: Array[float]) -> float:
        """Launches analog output scan with current (:obj:`AoParams`).
        Voltage data (voltage profiles) is taken from assigned buffer - 
        an 1D array of size number_of_channels * samples_per_channel. 
        
        For example, in case of using:

        AO ch1: :obj:`[1.0, 2.0, 3.0]` & AO ch2: :obj:`[0.0, 0.0, 0.0]` & AO ch3: :obj:`[0.5, 1.5, 2.5]`
        
        ao_buffer should be: :obj:`[1.0, 0.0, 0.5, 2.0, 0.0, 1.5, 3.0, 0.0, 2.5]`

        Args:
            ao_buffer (:obj:`Array[float]`): A buffer with double precision floating point sample values.

        Returns:
            scan rate in points per second, (:obj:`float`)
        """
        analog_range = ul.Range(self._params.range_id)
        samples_per_channel = int((len(ao_buffer) / (self._params.high_channel - self._params.low_channel + 1)))
        return self._ao_device.a_out_scan(self._params.low_channel, self._params.high_channel,
                                          analog_range, samples_per_channel,
                                          self._params.sample_rate, self._params.options, 
                                          self._params.scan_flags, ao_buffer)

    def iso_mode(self, ao_channel:int, voltage:float) -> float:
        """Sets voltage to the specified AO channel. 
        
        Note:
            The voltage remains on the channel until DAQ board released and disconnected.

        Args:
            ao_channel (:obj:`int`): AO channel number (usually from 0 to 3).
            
            voltage (:obj:`float`): voltage value, usually from 0 to 10.

        Returns:
            scan rate in points per second, (:obj:`float`)
        """
        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out(ao_channel,
                                    analog_range, 
                                    self._params.scan_flags,
                                    voltage)
