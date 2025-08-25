import logging
from typing import Tuple, List

# Use mock uldaq for development without hardware
from .mock_uldaq import uldaq as ul


class AiParams:
    """General class to represent main AI DAQ parameters. 
    Default parameters cannot be used to initialize uldaq.AiDevice,
    they need to be parsed from JSON file or specified manually.
    
    Parameters
    ----------
        sample_rate : :obj:`int`
            A/D sample rate in samples per channel per second.
        range_id : :obj:`uldaq.Range`
            Normally 5 for -10 to +10 Volts range. 
            Refer to :obj:`uldaq` for additional info.
        low_channel : :obj:`int`
            First A/D channel in the scan.
        high_channel : :obj:`int`
            Last A/D channel in the scan.
        input_mode : :obj:`uldaq.AiInputMode`
            The input mode of the specified channels.
            Refer to :obj:`uldaq` for additional info.
            By default, :obj:`uldaq.AiInputMode.SINGLE_ENDED` flag is used
        scan_flags : :obj:`uldaq.AOutScanFlag`
            One or more of the attributes (suitable for bit-wise operations) 
            specifying the conditioning applied to the data before it is returned.
            Refer to :obj:`uldaq` for additional info.
            By default, :obj:`uldaq.AOutScanFlag.DEFAULT` flag is used
        options : :obj:`uldaq.ScanOption`
            One or more of the attributes (suitable for bit-wise operations) 
            specifying the conditioning applied to the data before it is returned.
            Refer to :obj:`uldaq` for additional info.
            By default, :obj:`uldaq.ScanOption.CONTINUOUS` option is used

    """
    def __init__(self):
        self.sample_rate = -1  # Hz
        self.range_id = -1
        self.low_channel = -1
        self.high_channel = -1
        self.input_mode = ul.AiInputMode.SINGLE_ENDED  # 2
        self.scan_flags = ul.AInScanFlag.DEFAULT  # 0
        self.options = ul.ScanOption.CONTINUOUS  # 8

    def __str__(self):
        return str(vars(self))


class AiDeviceHandler:
    """Wraps the analog input :obj:`uldaq.AiDevice`.
    Initializes AI DAQ device, all parameters and buffer to write data.

    Parameters
    ----------
        ai_device_from_daq : :obj:`uldaq.AiDevice` 
            A class instance, obtained from :obj:`uldaq.DaqDevice`.
        params : :obj:`AiParams` 
            A class instance, containing all needed 
            analog input parameters parsed from JSON or specified manually.
        
    Raises
    ------
        :obj:`RuntimeError`
            If the DAQ device doesn't support analog input put or hardware paced analog input.
    
    """
    def __init__(self, ai_device_from_daq: ul.AiDevice,
                 params: AiParams):
        self._ai_device = ai_device_from_daq
        self._params = params
        self._check_device()
        self._init_buffer()

    def _check_device(self):
        if self._ai_device is None:
            error_str = "Error. DAQ device doesn't support analog input."
            logging.error(error_str)
            raise RuntimeError(error_str)

        info = self._ai_device.get_info()
        if not info.has_pacer():
            error_str = "Error. DAQ device doesn't support hardware paced analog input."
            logging.error(error_str)
            raise RuntimeError(error_str)

        if info.get_num_chans_by_mode(ul.AiInputMode.SINGLE_ENDED) <= 0:
            self._params.input_mode = ul.AiInputMode.DIFFERENTIAL

    def _init_buffer(self):
        channel_count = self._params.high_channel - self._params.low_channel + 1
        # For continuous scanning, create a buffer sized for 1 second of data
        # This is a reasonable default that can be adjusted based on actual scan parameters
        samples_per_channel = max(1000, self._params.sample_rate)  # At least 1 second worth of data
        self._buffer = ul.create_float_buffer(channel_count, samples_per_channel)

    def get(self) -> ul.AiDevice:
        """Provides explicit access to the uldaq.AiDevice.
        
        Returns
        ------- 
            :obj:`class` 
                :obj:`uldaq.AiDevice` class with properties and methods, 
                provided by :obj:`uldaq` library.
        """
        return self._ai_device                                   

    def get_buffer(self) -> List[float]:
        """Provides explicit access to buffer with current obtained A/D values.
        Buffer is an 1D array of size number_of_channels * samples_per_channel. 
        
        For example, in case of using channels 0-3, if ao_buffer is: 
        :obj:`[1.0, 0.0, 0.5, 2.0, 0.0, 1.5, 3.0, 0.0, 2.5]`, 
        data from each channel looks like: 
        AO ch1: :obj:`[1.0, 2.0, 3.0]` & AO ch2: :obj:`[0.0, 0.0, 0.0]` & AO ch3: :obj:`[0.5, 1.5, 2.5]`
        
        Returns
        ------- 
            :obj:`List[float]` 
                Returns an array of double precision floating point sample values.
                
        """
        return self._buffer

    def stop(self):
        """Interrupts analog input scan."""
        self._ai_device.scan_stop()
  
    def status(self) -> Tuple[ul.ScanStatus, ul.TransferStatus]:
        """Provides analog output scan and data transfer status.
        
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
        return self._ai_device.get_scan_status()

    # returns actual input scan rate
    def scan(self) -> float:
        """Launches analog input scan with current parameters from :obj:`AiParams`.

        Returns
        ------- 
            :obj:`float`
                Scan rate in points per second
        """
        analog_range = ul.Range(self._params.range_id)
        return self._ai_device.a_in_scan(self._params.low_channel, self._params.high_channel, 
                                         self._params.input_mode, analog_range, self._params.sample_rate,
                                         self._params.sample_rate, self._params.options, 
                                         self._params.scan_flags, self._buffer)
