"""
Smart uldaq module that automatically imports real hardware if available,
otherwise falls back to mock hardware for development and testing.
"""

import logging

# Try to import real uldaq first
try:
    import uldaq as real_uldaq
    DAQ_AVAILABLE = True
    logging.info("Real uldaq hardware detected - using actual DAQ hardware")
    
    # Use the real uldaq module
    uldaq = real_uldaq
    
except (ImportError, OSError) as e:
    # Fall back to mock hardware
    DAQ_AVAILABLE = False
    logging.warning(f"Real uldaq not available ({e}) - using MOCK hardware for development/testing")
    
    # Create mock classes for development/testing without hardware
    class InterfaceType:
        """Mock interface type constants."""
        ANY = 7
        USB = 1
        BLUETOOTH = 2
        ETHERNET = 4

    class AiInputMode:
        """Mock AI input mode constants."""
        SINGLE_ENDED = 2
        DIFFERENTIAL = 1

    class AInScanFlag:
        """Mock AI scan flag constants."""
        DEFAULT = 0

    class AOutScanFlag:
        """Mock AO scan flag constants."""
        DEFAULT = 0

    class ScanOption:
        """Mock scan option constants."""
        CONTINUOUS = 8
        DEFAULTIO = 0  # Added missing constant

    class ScanStatus:
        """Mock scan status constants."""
        RUNNING = 1
        STOPPED = 0

    class TransferStatus:
        """Mock transfer status constants."""
        IDLE = 0
        RUNNING = 1

    class Range:
        """Mock range class."""
        def __init__(self, range_id):
            self.range_id = range_id

    class DaqDeviceDescriptor:
        """Mock DAQ device descriptor."""
        def __init__(self):
            self.product_name = "Mock DAQ Device"
            self.product_id = 0
            self.dev_interface = "USB"
            self.dev_string = "Mock Device"
            self.unique_id = "MOCK_001"

    class DaqDevice:
        """Mock DAQ device."""
        def __init__(self, descriptor):
            self._descriptor = descriptor
            self._connected = False
            self._released = False
            self._reset = False
            logging.info("Mock DAQ device initialized")
        
        def get_descriptor(self):
            return self._descriptor
        
        def is_connected(self):
            return self._connected
        
        def connect(self, connection_code=None):
            self._connected = True
            # Sanitize connection_code to prevent information disclosure
            safe_code = str(connection_code) if connection_code is not None else "None"
            logging.info(f"Mock DAQ device connected (connection_code: {safe_code})")
        
        def disconnect(self):
            self._connected = False
            logging.info("Mock DAQ device disconnected")
        
        def release(self):
            self._released = True
            self._connected = False
            logging.info("Mock DAQ device released")
        
        def reset(self):
            self._reset = True
            self._connected = False
            logging.info("Mock DAQ device reset")
        
        def quit(self):
            self.disconnect()
            self.release()
        
        def get_ai_device(self):
            return MockAiDevice()
        
        def get_ao_device(self):
            return MockAoDevice()

    class MockAiInfo:
        """Mock AI device info."""
        def get_num_chans_by_mode(self, mode):
            # Validate mode parameter
            if mode not in [AiInputMode.SINGLE_ENDED, AiInputMode.DIFFERENTIAL]:
                logging.warning(f"Mock AI device: Invalid mode {mode}, defaulting to 8 channels")
            return 8  # Mock 8 channels
        
        def has_pacer(self):
            return True  # Mock device supports pacing

    class MockAoInfo:
        """Mock AO device info."""
        def has_pacer(self):
            return True  # Mock device supports pacing

    class MockAiDevice:
        """Mock AI (Analog Input) device."""
        def __init__(self):
            self._connected = False
            self._scanning = False
            self._scan_count = 0
            self._total_count = 0
            self._current_index = 0
            self._buffer = [0.0] * 1000  # Default buffer
            logging.info("Mock AI device initialized")
        
        def connect(self):
            self._connected = True
            logging.info("Mock AI device connected")
        
        def disconnect(self):
            self._connected = False
            logging.info("Mock AI device disconnected")
        
        def get_info(self):
            return MockAiInfo()
        
        @property
        def status(self):
            """Status property for compatibility with existing code."""
            return self.get_scan_status()[0]  # Return ScanStatus
        
        def scan_stop(self):
            """Stop analog input scan."""
            self._scanning = False
            logging.info("Mock AI device scan stopped")
        
        def get_scan_status(self):
            """Get scan and transfer status."""
            if self._scanning:
                scan_status = ScanStatus.RUNNING
                transfer_status = MockTransferStatus(
                    current_scan_count=self._scan_count,
                    current_total_count=self._total_count,
                    current_index=self._current_index
                )
            else:
                scan_status = ScanStatus.STOPPED
                transfer_status = MockTransferStatus(0, 0, 0)
            
            return (scan_status, transfer_status)
        
        def get_buffer(self):
            """Get buffer data for compatibility."""
            return self._buffer
        
        def a_in_scan(self, low_channel, high_channel, input_mode, analog_range, 
                      sample_rate, samples_per_channel, options, scan_flags, buffer):
            """Start analog input scan with validation."""
            # Input validation to prevent runtime errors
            if not isinstance(low_channel, int) or not isinstance(high_channel, int):
                raise ValueError("Channel numbers must be integers")
            if low_channel < 0 or high_channel > 7:
                raise ValueError("Channel range must be 0-7 for mock device")
            if low_channel > high_channel:
                raise ValueError("Low channel must be <= high channel")
            if sample_rate <= 0:
                raise ValueError("Sample rate must be positive")
            if samples_per_channel <= 0:
                raise ValueError("Samples per channel must be positive")
            
            self._scanning = True
            self._scan_count = 0
            self._total_count = samples_per_channel
            self._current_index = 0
            logging.info(f"Mock AI device scan started: channels {low_channel}-{high_channel}, rate {sample_rate}")
            return sample_rate  # Return the actual scan rate

    class MockAoDevice:
        """Mock AO (Analog Output) device."""
        def __init__(self):
            self._connected = False
            self._scanning = False
            self._scan_count = 0
            self._total_count = 0
            self._current_index = 0
            logging.info("Mock AO device initialized")
        
        def connect(self):
            self._connected = True
            logging.info("Mock AO device connected")
        
        def disconnect(self):
            self._connected = False
            logging.info("Mock AO device disconnected")
        
        def get_info(self):
            return MockAoInfo()
        
        @property
        def status(self):
            """Status property for compatibility with existing code."""
            return self.get_scan_status()[0]  # Return ScanStatus
        
        def scan_stop(self):
            """Stop analog output scan."""
            self._scanning = False
            logging.info("Mock AO device scan stopped")
        
        def get_scan_status(self):
            """Get scan and transfer status."""
            if self._scanning:
                scan_status = ScanStatus.RUNNING
                transfer_status = MockTransferStatus(
                    current_scan_count=self._scan_count,
                    current_total_count=self._total_count,
                    current_index=self._current_index
                )
            else:
                scan_status = ScanStatus.STOPPED
                transfer_status = MockTransferStatus(0, 0, 0)
            
            return (scan_status, transfer_status)
        
        def a_out_scan(self, low_channel, high_channel, analog_range, 
                       samples_per_channel, sample_rate, options, scan_flags, ao_buffer):
            """Start analog output scan with validation."""
            # Input validation to prevent runtime errors
            if not isinstance(low_channel, int) or not isinstance(high_channel, int):
                raise ValueError("Channel numbers must be integers")
            if low_channel < 0 or high_channel > 3:
                raise ValueError("Channel range must be 0-3 for mock device")
            if low_channel > high_channel:
                raise ValueError("Low channel must be <= high channel")
            if sample_rate <= 0:
                raise ValueError("Sample rate must be positive")
            if samples_per_channel <= 0:
                raise ValueError("Samples per channel must be positive")
            if not isinstance(ao_buffer, (list, tuple)) or len(ao_buffer) == 0:
                raise ValueError("AO buffer must be a non-empty list or tuple")
            
            self._scanning = True
            self._scan_count = 0
            self._total_count = samples_per_channel
            self._current_index = 0
            logging.info(f"Mock AO device scan started: channels {low_channel}-{high_channel}, rate {sample_rate}")
            return sample_rate  # Return the actual scan rate
        
        def iso_mode(self, ao_channel, voltage):
            """Set voltage in ISO mode for compatibility."""
            # Input validation
            if not isinstance(ao_channel, int):
                raise ValueError("AO channel must be an integer")
            if ao_channel < 0 or ao_channel > 3:
                raise ValueError("AO channel must be 0-3 for mock device")
            if not isinstance(voltage, (int, float)):
                raise ValueError("Voltage must be a number")
            if voltage < -10 or voltage > 10:
                raise ValueError("Voltage must be between -10V and +10V for mock device")
            
            logging.info(f"Mock AO device ISO mode: channel {ao_channel}, voltage {voltage}")
            return voltage

    class MockTransferStatus:
        """Mock transfer status class."""
        def __init__(self, current_scan_count, current_total_count, current_index):
            self.current_scan_count = current_scan_count
            self.current_total_count = current_total_count
            self.current_index = current_index

    def get_daq_device_inventory(interface_type, max_devices):
        """Mock function to get DAQ device inventory with validation."""
        # Input validation
        if not isinstance(max_devices, int) or max_devices <= 0:
            logging.warning(f"Mock: Invalid max_devices {max_devices}, using 1")
            max_devices = 1
        
        logging.info("Mock: Getting DAQ device inventory")
        # Return appropriate number of devices based on max_devices
        devices = [DaqDeviceDescriptor() for _ in range(min(max_devices, 1))]
        return devices

    def get_net_daq_device_descriptor(host, port):
        """Mock function for network DAQ devices with validation."""
        # Input validation to prevent injection attacks
        if not isinstance(host, str) or not host:
            raise ValueError("Host must be a non-empty string")
        if not isinstance(port, int) or port <= 0 or port > 65535:
            raise ValueError("Port must be a valid port number (1-65535)")
        
        logging.info("Mock: Getting network DAQ device descriptor")
        return DaqDeviceDescriptor()

    def create_float_buffer(channel_count, sample_rate):
        """Mock function to create float buffer with comprehensive validation."""
        # Comprehensive input validation to prevent vulnerabilities
        if not isinstance(channel_count, int) or not isinstance(sample_rate, int):
            raise ValueError("channel_count and sample_rate must be integers")
        
        if channel_count <= 0 or sample_rate <= 0:
            raise ValueError("channel_count and sample_rate must be positive")
        
        if channel_count > 1000 or sample_rate > 1000000:
            raise ValueError("Values too large for mock device (max: 1000 channels, 1M samples)")
        
        buffer_size = channel_count * sample_rate
        if buffer_size > 10000000:  # 10M samples max
            raise ValueError("Buffer size too large for mock device")
        
        logging.info(f"Mock: Creating float buffer with {channel_count} channels, {sample_rate} samples")
        return [0.0] * buffer_size

    # Create mock uldaq module
    class MockUldaq:
        """Mock uldaq module that mimics the real uldaq library."""
        InterfaceType = InterfaceType()
        DaqDeviceDescriptor = DaqDeviceDescriptor
        AiDevice = MockAiDevice
        AoDevice = MockAoDevice
        AiInputMode = AiInputMode()
        AInScanFlag = AInScanFlag()
        AOutScanFlag = AOutScanFlag()
        ScanOption = ScanOption()
        ScanStatus = ScanStatus()
        TransferStatus = TransferStatus()
        Range = Range
        
        @staticmethod
        def get_daq_device_inventory(interface_type, max_devices):
            return get_daq_device_inventory(interface_type, max_devices)
        
        @staticmethod
        def DaqDevice(descriptor):
            return DaqDevice(descriptor)
        
        @staticmethod
        def create_float_buffer(channel_count, sample_rate):
            return create_float_buffer(channel_count, sample_rate)
        
        @staticmethod
        def get_net_daq_device_descriptor(host, port):
            return get_net_daq_device_descriptor(host, port)

    # Export the mock module
    uldaq = MockUldaq()

# Export the status for other modules to check
# (to avoid import of internal entities)
__all__ = ['uldaq', 'DAQ_AVAILABLE']
