"""
Smart uldaq module that automatically imports real hardware if available,
otherwise falls back to mock hardware for development and testing.
"""

import logging

# Try to import real uldaq first
try:
    import uldaq as real_uldaq
    UDAQ_AVAILABLE = True
    logging.info("Real uldaq hardware detected - using actual DAQ hardware")
    
    # Use the real uldaq module
    uldaq = real_uldaq
    
except (ImportError, OSError) as e:
    # Fall back to mock hardware
    UDAQ_AVAILABLE = False
    logging.warning(f"Real uldaq not available ({e}) - using MOCK hardware for development/testing")
    logging.warning("This is normal for development without hardware or missing drivers")
    
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
            logging.info("Mock DAQ device initialized")
        
        def get_descriptor(self):
            return self._descriptor
        
        def is_connected(self):
            return self._connected
        
        def connect(self, connection_code=None):
            self._connected = True
            logging.info(f"Mock DAQ device connected (connection_code: {connection_code})")
        
        def disconnect(self):
            self._connected = False
            logging.info("Mock DAQ device disconnected")
        
        def quit(self):
            self.disconnect()
        
        def get_ai_device(self):
            return MockAiDevice()
        
        def get_ao_device(self):
            return MockAoDevice()

    class MockAiDevice:
        """Mock AI (Analog Input) device."""
        def __init__(self):
            logging.info("Mock AI device initialized")
        
        def connect(self):
            logging.info("Mock AI device connected")
        
        def disconnect(self):
            logging.info("Mock AI device disconnected")
        
        def get_info(self):
            return MockAiInfo()

    class MockAiInfo:
        """Mock AI device info."""
        def get_num_chans_by_mode(self, mode):
            return 8  # Mock 8 channels

    class MockAoDevice:
        """Mock AO (Analog Output) device."""
        def __init__(self):
            logging.info("Mock AO device initialized")
        
        def connect(self):
            logging.info("Mock AO device connected")
        
        def disconnect(self):
            logging.info("Mock AO device disconnected")

    def get_daq_device_inventory(interface_type, max_devices):
        """Mock function to get DAQ device inventory."""
        logging.info("Mock: Getting DAQ device inventory")
        return [DaqDeviceDescriptor()]

    def get_net_daq_device_descriptor(host, port):
        """Mock function for network DAQ devices."""
        logging.info("Mock: Getting network DAQ device descriptor")
        return DaqDeviceDescriptor()

    def create_float_buffer(channel_count, sample_rate):
        """Mock function to create float buffer."""
        logging.info(f"Mock: Creating float buffer with {channel_count} channels, {sample_rate} samples")
        return [0.0] * channel_count * sample_rate

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

    # Export the mock module
    uldaq = MockUldaq()

# Export the status for other modules to check
__all__ = ['uldaq', 'UDAQ_AVAILABLE']
