import logging
from typing import Tuple, List

# Use mock uldaq for development without hardware
from .mock_uldaq import uldaq as ul


class AoParams:
    """General class to represent main AO DAQ parameters. 
    Default parameters cannot be used to initialize uldaq.AoDevice,
    they need to be parsed from JSON file or specified manually.
    
    Parameters
    ----------
        sample_rate : :obj:`int`
            Number of D/A samples to output.
        range_id : :obj:`uldaq.Range`
            Normally 5 for -10 to +10 Volts range. 
            Refer to :obj:`uldaq` for additional info.
        low_channel : :obj:`int`
            First D/A channel in the scan.
        high_channel : :obj:`int`
            Last D/A channel in the scan.
        scan_flags : :obj:`uldaq.AOutScanFlag`
            One or more of the attributes (suitable for bit-wise operations) 
            specifying the conditioning applied to the data.
            Refer to :obj:`uldaq` for additional info.
            By default, :obj:`uldaq.AOutScanFlag.DEFAULT` flag is used
        options : :obj:`uldaq.ScanOption`
            One or more of the attributes (suitable for bit-wise operations) 
            specifying the conditioning applied to the data.
            Refer to :obj:`uldaq` for additional info.
            By default, :obj:`uldaq.ScanOption.CONTINUOUS` option is used

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
    """Wraps the analog output :obj:`uldaq.AoDevice`.
    Initializes AO DAQ device and all parameters.

    Parameters
    ----------
        ao_device_from_daq : :obj:`uldaq.AoDevice`
            A class instance, obtained from :obj:`uldaq.DaqDevice`.
        params : :obj:`AoParams` 
            A class instance, containing all needed 
            analog output parameters parsed from JSON or specified manually.
        
    Raises
    ------
        :obj:`RuntimeError`
            If the DAQ device doesn't support analog output or hardware paced analog output.
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
        """Provides explicit access to the uldaq.AoDevice.
        
        Returns
        ------- 
            :obj:`class` 
                :obj:`uldaq.AoDevice` class with properties and methods, 
                provided by :obj:`uldaq` library.
        """
        return self._ao_device

    def stop(self):
        """Interrupts analog output scan"""
        self._ao_device.scan_stop()

    def status(self) -> Tuple[ul.ScanStatus, ul.TransferStatus]:
        """Provides analog output scan and data transfer status
        
        Returns
        ------- 
            :obj:`tuple` 
                :obj:`(uldaq.ScanStatus, uldaq.TransferStatus)` tuple 
                with first element that can be IDLE = 0 or RUNNING = 1. 
                The second element is a class containing properties that 
                define the progress of a scan operation:
                :obj:`current_scan_count`, :obj:`current_total_count` and 
                :obj:`current_index`.

        """
        return self._ao_device.get_scan_status()

    def scan(self, ao_buffer: List[float]) -> float:
        """Launches analog output scan with current parameters from :obj:`AoParams`.
        Voltage data (voltage profiles) is taken from assigned buffer - 
        an 1D array of size number_of_channels * samples_per_channel. 
        
        For example, in case of using:

        AO ch0: :obj:`[1.0, 2.0, 3.0]` & AO ch1: :obj:`[0.0, 0.0, 0.0]` & AO ch2: :obj:`[0.5, 1.5, 2.5]`
        
        ao_buffer should be: :obj:`[1.0, 0.0, 0.5, 2.0, 0.0, 1.5, 3.0, 0.0, 2.5]`

        Args
        ----
            ao_buffer : :obj:`List[float]`
                A buffer with double precision floating point sample values.

        Returns
        ------- 
            :obj:`float`
                Scan rate in points per second
        """
        analog_range = ul.Range(self._params.range_id)
        samples_per_channel = int((len(ao_buffer) / (self._params.high_channel - self._params.low_channel + 1)))
        return self._ao_device.a_out_scan(self._params.low_channel, self._params.high_channel,
                                          analog_range, samples_per_channel,
                                          self._params.sample_rate, self._params.options, 
                                          self._params.scan_flags, ao_buffer)

    def iso_mode(self, ao_channel:int, voltage:float) -> float:
        """Sets voltage to the specified AO channel. 
        
        Note
        ----
            The voltage remains on the channel until DAQ board released and disconnected.

        Args
        ----
            ao_channel : :obj:`int`
                AO channel number (usually from 0 to 3).

            voltage : :obj:`float`
                Voltage value, usually from 0 to 10.

        Returns
        -------
            :obj:`float`
                Scan rate in points per second
        """
        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out(ao_channel,
                                     analog_range,
                                     self._params.scan_flags,
                                     voltage)
