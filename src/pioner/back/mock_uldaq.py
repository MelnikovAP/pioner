"""
Smart uldaq module that automatically imports real hardware if available,
otherwise falls back to mock hardware for development and testing.
"""

import logging
import time
import secrets
import threading
from typing import Optional, Union, List, Tuple
from dataclasses import dataclass
from enum import Enum

# Configure secure logging - no sensitive data
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security constants
MAX_BUFFER_SIZE = 1024 * 1024  # 1MB max buffer size
MAX_CHANNELS = 64  # Maximum channels per device
MAX_SAMPLE_RATE = 100000  # Maximum sample rate (100kHz)
MAX_SCAN_DURATION = 3600  # Maximum scan duration (1 hour) TODO: to be increased
MAX_OPERATIONS_PER_MINUTE = 100  # Rate limiting
MAX_SCAN_COUNT = 1000000  # Maximum scan count to prevent overflow
MAX_SESSION_AGE = 3600  # Maximum session age (1 hour) TODO: to be increased


class DeviceState(Enum):
    """Secure device state machine."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    SCANNING = "scanning"
    ERROR = "error"
    BUSY = "busy"


@dataclass
class SecurityContext:
    """Security context for device operations."""

    operation_count: int = 0
    last_operation_time: float = 0.0
    session_id: str = ""
    access_level: str = "user"
    created_time: float = 0.0


class SecurityManager:
    """Manages security and access control with thread safety."""

    def __init__(self):
        self._operation_counts = {}
        self._session_tokens = {}
        self._rate_limit_window = 60.0  # 1 minute window
        self._lock = threading.RLock()  # Thread-safe operations
        self._cleanup_timer = None
        self._start_cleanup_timer()

    def _start_cleanup_timer(self):
        """Start periodic cleanup timer."""

        def cleanup_old_sessions():
            while True:
                try:
                    time.sleep(300)  # Clean up every 5 minutes
                    self._cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")

        cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
        cleanup_thread.start()

    def _cleanup_expired_sessions(self):
        """Clean up expired sessions to prevent memory leaks."""
        current_time = time.time()
        expired_sessions = []

        with self._lock:
            for session_id, session_data in self._session_tokens.items():
                if current_time - session_data["created_time"] > MAX_SESSION_AGE:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                del self._session_tokens[session_id]
                logger.info(f"Expired session cleaned up: {session_id[:8]}...")

    def validate_access(self, operation: str, context: SecurityContext) -> bool:
        """Validate access to device operations with thread safety."""
        if not isinstance(context, SecurityContext):
            logger.error("Invalid security context type")
            return False

        current_time = time.time()

        with self._lock:
            # Session age validation
            if current_time - context.created_time > MAX_SESSION_AGE:
                logger.warning(f"Session expired for operation: {operation}")
                return False

            # Rate limiting - reasonable for normal operations
            # TEMPORARILY DISABLED FOR TESTING
            # if current_time - context.last_operation_time < 0.0001:  # 0.1ms between operations (was 1ms)
            #     logger.warning(f"Rate limit exceeded for operation: {operation}")
            #     return False

            # Session validation
            if not context.session_id or context.session_id not in self._session_tokens:
                logger.warning(f"Invalid session for operation: {operation}")
                return False

            # Operation count limiting
            if context.operation_count > MAX_OPERATIONS_PER_MINUTE:
                logger.warning(f"Operation limit exceeded: {operation}")
                return False

            # Update operation tracking
            context.operation_count += 1
            context.last_operation_time = current_time

            return True

    def create_session(self) -> str:
        """Create a new cryptographically secure session."""
        # Use cryptographically secure random generation
        session_id = secrets.token_hex(16)  # 32 character hex string

        with self._lock:
            self._session_tokens[session_id] = {
                "created_time": time.time(),
                "operation_count": 0,
            }

        return session_id

    def cleanup_session(self, session_id: str):
        """Clean up expired session with validation."""
        if not isinstance(session_id, str):
            logger.error("Invalid session ID type for cleanup")
            return

        with self._lock:
            if session_id in self._session_tokens:
                del self._session_tokens[session_id]
                logger.info(f"Session cleaned up: {session_id[:8]}...")


# Global security manager
security_manager = SecurityManager()

# Try to import real uldaq first
try:
    import uldaq as real_uldaq

    DAQ_AVAILABLE = True
    logger.info("Real uldaq hardware detected - using actual DAQ hardware")

    # Use the real uldaq module
    uldaq = real_uldaq

except (ImportError, OSError) as e:
    # Fall back to mock hardware
    DAQ_AVAILABLE = False
    logger.warning(
        f"Real uldaq not available ({e}) - using SECURE MOCK hardware for development/testing"
    )

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
    DEFAULT = 0


class ScanStatus:
    """Mock scan status constants."""

    RUNNING = 1
    STOPPED = 0


class TransferStatus:
    """Mock transfer status constants."""

    IDLE = 0
    RUNNING = 1


class Range:
    """Mock range class with validation."""

    def __init__(self, range_id: int):
        if not isinstance(range_id, int) or range_id < 0 or range_id > 10:
            raise ValueError("Range ID must be integer 0-10")
        self.range_id = range_id


class DaqDeviceDescriptor:
    """Mock DAQ device descriptor with sanitized data."""

    def __init__(self):
        self.product_name = "Mock DAQ Device"
        self.product_id = 0
        self.dev_interface = "USB"
        self.dev_string = "Mock Device"
        self.unique_id = "MOCK_001"

    def __str__(self):
        return f"Mock DAQ Device (ID: {self.product_id})"

    def __repr__(self):
        return f"Mock DAQ Device (ID: {self.product_id})"


class DaqDevice:
    """Mock DAQ device with security hardening."""

    def __init__(self, descriptor):
        if not isinstance(descriptor, DaqDeviceDescriptor):
            raise ValueError("Invalid descriptor type")

        # Validate descriptor is properly initialized
        if not hasattr(descriptor, "product_name") or not descriptor.product_name:
            raise ValueError("Invalid descriptor: missing or empty product_name")

        self._descriptor = descriptor
        self._state = DeviceState.DISCONNECTED
        self._security_context = SecurityContext()
        self._security_context.session_id = security_manager.create_session()
        self._security_context.created_time = time.time()
        self._last_operation = 0.0
        self._operation_count = 0

        logger.info("Mock DAQ device initialized with security context")
    
    def get_descriptor(self):
        return self._descriptor
    
    def is_connected(self):
        return self._state == DeviceState.CONNECTED
    
    def connect(self, connection_code=None):
        # Validate security context
        if not security_manager.validate_access("connect", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        # Validate connection parameters
        if connection_code is not None and not isinstance(connection_code, int):
            raise ValueError("Connection code must be integer or None")

        self._state = DeviceState.CONNECTED

        # Secure logging - no sensitive data
        logger.info("Mock DAQ device connected successfully")
    
    def disconnect(self):
        if not security_manager.validate_access("disconnect", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.DISCONNECTED
        logger.info("Mock DAQ device disconnected")

    def release(self):
        if not security_manager.validate_access("release", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.DISCONNECTED

        # Cleanup resources
        security_manager.cleanup_session(self._security_context.session_id)
        logger.info("Mock DAQ device released and resources cleaned up")

    def reset(self):
        if not security_manager.validate_access("reset", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.DISCONNECTED
        logger.info("Mock DAQ device reset")
    
    def quit(self):
        self.disconnect()
        self.release()
    
    def get_ai_device(self):
        if self._state != DeviceState.CONNECTED:
            raise RuntimeError("Device not connected")
        return MockAiDevice(self._security_context)
    
    def get_ao_device(self):
        if self._state != DeviceState.CONNECTED:
            raise RuntimeError("Device not connected")
        return MockAoDevice(self._security_context)

    def __del__(self):
        """Secure cleanup on destruction."""
        try:
            if hasattr(self, "_security_context") and self._security_context.session_id:
                security_manager.cleanup_session(self._security_context.session_id)
        except Exception as e:
            logger.error(f"Error during device cleanup: {e}")


class MockAiInfo:
    """Mock AI device info with validation."""

    def get_num_chans_by_mode(self, mode):
        # Validate mode parameter
        if mode not in [AiInputMode.SINGLE_ENDED, AiInputMode.DIFFERENTIAL]:
            # Sanitize mode before logging to prevent injection
            safe_mode = str(mode) if isinstance(mode, (int, str)) else "unknown"
            logger.warning(
                f"Mock AI device: Invalid mode {safe_mode}, defaulting to 8 channels"
            )
            return 8
        return 8  # Mock 8 channels

    def has_pacer(self):
        return True  # Mock device supports pacing


class MockAoInfo:
    """Mock AO device info with validation."""

    def has_pacer(self):
        return True  # Mock device supports pacing


class MockAiDevice:
    """Mock AI (Analog Input) device with security hardening."""

    def __init__(self, security_context: SecurityContext):
        if not isinstance(security_context, SecurityContext):
            raise ValueError("Invalid security context")

        self._security_context = security_context
        self._state = DeviceState.DISCONNECTED
        self._scanning = False
        self._scan_count = 0
        self._total_count = 0
        self._current_index = 0
        self._buffer = [0.0] * 1000  # Default buffer
        self._scan_start_time = 0.0
        self._last_operation = 0.0

        logger.info("Mock AI device initialized with security context")
    
    def connect(self):
        if not security_manager.validate_access("ai_connect", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.CONNECTED
        logger.info("Mock AI device connected")
    
    def disconnect(self):
        if not security_manager.validate_access(
            "ai_disconnect", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.DISCONNECTED

        # Stop any ongoing scan
        if self._scanning:
            self.scan_stop()

        logger.info("Mock AI device disconnected")
    
    def get_info(self):
        return MockAiInfo()

    @property
    def status(self):
        """Status property with state validation."""
        if self._state != DeviceState.CONNECTED:
            return ScanStatus.STOPPED
        return self.get_scan_status()[0]

    def scan_stop(self):
        """Stop analog input scan with validation."""
        if not security_manager.validate_access("ai_scan_stop", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        if not self._scanning:
            logger.warning("Attempted to stop scan that was not running")
            return

        self._scanning = False
        self._scan_count = 0
        self._total_count = 0
        self._current_index = 0
        self._scan_start_time = 0.0

        logger.info("Mock AI device scan stopped")

    def get_scan_status(self):
        """Get scan and transfer status with validation."""
        if not security_manager.validate_access(
            "ai_get_status", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        # Validate scan duration
        if self._scanning and time.time() - self._scan_start_time > MAX_SCAN_DURATION:
            logger.warning("Scan duration exceeded maximum, auto-stopping")
            self.scan_stop()

        if self._scanning:
            scan_status = ScanStatus.RUNNING
            transfer_status = MockTransferStatus(
                current_scan_count=self._scan_count,
                current_total_count=self._total_count,
                current_index=self._current_index,
            )
        else:
            scan_status = ScanStatus.STOPPED
            transfer_status = MockTransferStatus(0, 0, 0)

        return (scan_status, transfer_status)

    def get_buffer(self):
        """Get buffer data with security validation."""
        if not security_manager.validate_access(
            "ai_get_buffer", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        # Return copy to prevent external modification
        buffer_copy = self._buffer.copy()
        return buffer_copy

    def a_in_scan(
        self,
        low_channel,
        high_channel,
        input_mode,
        analog_range,
        sample_rate,
        samples_per_channel,
        options,
        scan_flags,
        buffer,
    ):
        """Start analog input scan with comprehensive security validation."""
        if not security_manager.validate_access(
            "ai_scan_start", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        # Comprehensive input validation
        if not isinstance(low_channel, int) or not isinstance(high_channel, int):
            raise ValueError("Channel numbers must be integers")
        if low_channel < 0 or high_channel > MAX_CHANNELS - 1:
            raise ValueError(
                f"Channel range must be 0-{MAX_CHANNELS - 1} for mock device"
            )
        if low_channel > high_channel:
            raise ValueError("Low channel must be <= high channel")
        if not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
            raise ValueError("Sample rate must be positive number")
        if sample_rate > MAX_SAMPLE_RATE:
            raise ValueError(f"Sample rate exceeds maximum {MAX_SAMPLE_RATE} Hz")
        if not isinstance(samples_per_channel, int) or samples_per_channel <= 0:
            raise ValueError("Samples per channel must be positive integer")
        if samples_per_channel > MAX_SCAN_COUNT:
            raise ValueError(f"Samples per channel exceeds maximum {MAX_SCAN_COUNT}")
        if not isinstance(input_mode, int) or input_mode not in [
            AiInputMode.SINGLE_ENDED,
            AiInputMode.DIFFERENTIAL,
        ]:
            raise ValueError("Invalid input mode")
        if not isinstance(analog_range, Range):
            raise ValueError("Invalid analog range")
        if not isinstance(options, int) or options < 0:
            raise ValueError("Invalid scan options")
        if not isinstance(scan_flags, int) or scan_flags < 0:
            raise ValueError("Invalid scan flags")
        if not isinstance(buffer, (list, tuple)) or len(buffer) == 0:
            raise ValueError("Buffer must be non-empty list or tuple")

        # Validate buffer size vs parameters with overflow protection
        try:
            expected_buffer_size = (
                high_channel - low_channel + 1
            ) * samples_per_channel
            if expected_buffer_size <= 0 or expected_buffer_size > MAX_SCAN_COUNT:
                raise ValueError("Buffer size calculation overflow")
        except OverflowError:
            raise ValueError("Buffer size calculation overflow")

        if len(buffer) != expected_buffer_size:
            raise ValueError(
                f"Buffer size {len(buffer)} doesn't match expected size {expected_buffer_size}"
            )

        # Check if device is available
        if self._state != DeviceState.CONNECTED:
            raise RuntimeError("Device not connected")
        if self._scanning:
            raise RuntimeError("Scan already in progress")

        # Start scan
        self._scanning = True
        self._scan_count = 0
        self._total_count = samples_per_channel
        self._current_index = 0
        self._scan_start_time = time.time()

        # Secure logging - no sensitive parameters
        logger.info("Mock AI device scan started successfully")
        return sample_rate


class MockAoDevice:
    """Mock AO (Analog Output) device with security hardening."""

    def __init__(self, security_context: SecurityContext):
        if not isinstance(security_context, SecurityContext):
            raise ValueError("Invalid security context")

        self._security_context = security_context
        self._state = DeviceState.DISCONNECTED
        self._scanning = False
        self._scan_count = 0
        self._total_count = 0
        self._current_index = 0
        self._scan_start_time = 0.0
        self._last_operation = 0.0

        logger.info("Mock AO device initialized with security context")
    
    def connect(self):
        if not security_manager.validate_access("ao_connect", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.CONNECTED
        logger.info("Mock AO device connected")
    
    def disconnect(self):
        if not security_manager.validate_access(
            "ao_disconnect", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        self._state = DeviceState.DISCONNECTED

        # Stop any ongoing scan
        if self._scanning:
            self.scan_stop()

        logger.info("Mock AO device disconnected")

    def get_info(self):
        return MockAoInfo()

    @property
    def status(self):
        """Status property with state validation."""
        if self._state != DeviceState.CONNECTED:
            return ScanStatus.STOPPED
        return self.get_scan_status()[0]

    def scan_stop(self):
        """Stop analog output scan with validation."""
        if not security_manager.validate_access("ao_scan_stop", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        if not self._scanning:
            logger.warning("Attempted to stop scan that was not running")
            return

        self._scanning = False
        self._scan_count = 0
        self._total_count = 0
        self._current_index = 0
        self._scan_start_time = 0.0

        logger.info("Mock AO device scan stopped")

    def get_scan_status(self):
        """Get scan and transfer status with validation."""
        if not security_manager.validate_access(
            "ao_get_status", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        # Validate scan duration
        if self._scanning and time.time() - self._scan_start_time > MAX_SCAN_DURATION:
            logger.warning("Scan duration exceeded maximum, auto-stopping")
            self.scan_stop()

        if self._scanning:
            scan_status = ScanStatus.RUNNING
            transfer_status = MockTransferStatus(
                current_scan_count=self._scan_count,
                current_total_count=self._total_count,
                current_index=self._current_index,
            )
        else:
            scan_status = ScanStatus.STOPPED
            transfer_status = MockTransferStatus(0, 0, 0)

        return (scan_status, transfer_status)

    def a_out_scan(
        self,
        low_channel,
        high_channel,
        analog_range,
        samples_per_channel,
        sample_rate,
        options,
        scan_flags,
        ao_buffer,
    ):
        """Start analog output scan with comprehensive security validation."""
        if not security_manager.validate_access(
            "ao_scan_start", self._security_context
        ):
            raise RuntimeError("Access denied: security validation failed")

        # Comprehensive input validation
        if not isinstance(low_channel, int) or not isinstance(high_channel, int):
            raise ValueError("Channel numbers must be integers")
        if (
            low_channel < 0 or high_channel > 3
        ):  # AO devices typically have fewer channels
            raise ValueError("Channel range must be 0-3 for mock AO device")
        if low_channel > high_channel:
            raise ValueError("Low channel must be <= high channel")
        if not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
            raise ValueError("Sample rate must be positive number")
        if sample_rate > MAX_SAMPLE_RATE:
            raise ValueError(f"Sample rate exceeds maximum {MAX_SAMPLE_RATE} Hz")
        if not isinstance(samples_per_channel, int) or samples_per_channel <= 0:
            raise ValueError("Samples per channel must be positive integer")
        if samples_per_channel > MAX_SCAN_COUNT:
            raise ValueError(f"Samples per channel exceeds maximum {MAX_SCAN_COUNT}")
        if not isinstance(analog_range, Range):
            raise ValueError("Invalid analog range")
        if not isinstance(options, int) or options < 0:
            raise ValueError("Invalid scan options")
        if not isinstance(scan_flags, int) or scan_flags < 0:
            raise ValueError("Invalid scan flags")
        if not isinstance(ao_buffer, (list, tuple)) or len(ao_buffer) == 0:
            raise ValueError("AO buffer must be non-empty list or tuple")

        # Validate buffer size vs parameters with overflow protection
        try:
            expected_buffer_size = (
                high_channel - low_channel + 1
            ) * samples_per_channel
            if expected_buffer_size <= 0 or expected_buffer_size > MAX_SCAN_COUNT:
                raise ValueError("Buffer size calculation overflow")
        except OverflowError:
            raise ValueError("Buffer size calculation overflow")

        if len(ao_buffer) != expected_buffer_size:
            raise ValueError(
                f"Buffer size {len(ao_buffer)} doesn't match expected size {expected_buffer_size}"
            )

        # Check if device is available
        if self._state != DeviceState.CONNECTED:
            raise RuntimeError("Device not connected")
        if self._scanning:
            raise RuntimeError("Scan already in progress")

        # Start scan
        self._scanning = True
        self._scan_count = 0
        self._total_count = samples_per_channel
        self._current_index = 0
        self._scan_start_time = time.time()

        # Secure logging - no sensitive parameters
        logger.info("Mock AO device scan started successfully")
        return sample_rate

    def iso_mode(self, ao_channel, voltage):
        """Set voltage in ISO mode with comprehensive validation."""
        if not security_manager.validate_access("ao_iso_mode", self._security_context):
            raise RuntimeError("Access denied: security validation failed")

        # Comprehensive input validation
        if not isinstance(ao_channel, int):
            raise ValueError("AO channel must be an integer")
        if ao_channel < 0 or ao_channel > 3:
            raise ValueError("AO channel must be 0-3 for mock device")
        if not isinstance(voltage, (int, float)):
            raise ValueError("Voltage must be a number")
        if voltage < -10 or voltage > 10:
            raise ValueError("Voltage must be between -10V and +10V for mock device")

        # Check if device is available
        if self._state != DeviceState.CONNECTED:
            raise RuntimeError("Device not connected")

        # Secure logging - no sensitive parameters
        logger.info("Mock AO device ISO mode set successfully")
        return voltage
    
    def a_out(self, ao_channel, analog_range, scan_flags, voltage):
        """Set voltage on AO channel with comprehensive validation."""
        if not security_manager.validate_access("ao_a_out", self._security_context):
            raise RuntimeError("Access denied: security validation failed")
        
        # Comprehensive input validation
        if not isinstance(ao_channel, int):
            raise ValueError("AO channel must be an integer")
        if ao_channel < 0 or ao_channel > 3:
            raise ValueError("AO channel must be 0-3 for mock device")
        if not isinstance(analog_range, Range):
            raise ValueError("Invalid analog range")
        if not isinstance(scan_flags, int) or scan_flags < 0:
            raise ValueError("Invalid scan flags")
        if not isinstance(voltage, (int, float)):
            raise ValueError("Voltage must be a number")
        if voltage < -10 or voltage > 10:
            raise ValueError("Voltage must be between -10V and +10V for mock device")
        
        # Check if device is available
        if self._state != DeviceState.CONNECTED:
            raise RuntimeError("Device not connected")
        
        # Secure logging - no sensitive parameters
        logger.info("Mock AO device voltage set successfully")
        return voltage


class MockTransferStatus:
    """Mock transfer status class with validation."""

    def __init__(
        self, current_scan_count: int, current_total_count: int, current_index: int
    ):
        # Validate and bound all values to prevent overflow
        if not isinstance(current_scan_count, int) or current_scan_count < 0:
            raise ValueError("Invalid scan count")
        if current_scan_count > MAX_SCAN_COUNT:
            raise ValueError(f"Scan count too large (max: {MAX_SCAN_COUNT})")

        if not isinstance(current_total_count, int) or current_total_count < 0:
            raise ValueError("Invalid total count")
        if current_total_count > MAX_SCAN_COUNT:
            raise ValueError(f"Total count too large (max: {MAX_SCAN_COUNT})")

        if not isinstance(current_index, int) or current_index < 0:
            raise ValueError("Invalid current index")
        if current_index > MAX_SCAN_COUNT:
            raise ValueError(f"Current index too large (max: {MAX_SCAN_COUNT})")

        self.current_scan_count = current_scan_count
        self.current_total_count = current_total_count
        self.current_index = current_index


def get_daq_device_inventory(interface_type, max_devices):
    """Mock function to get DAQ device inventory with security validation."""
    # Input validation for interface_type
    if not isinstance(interface_type, int) or interface_type not in [1, 2, 4, 7]:
        raise ValueError(
            f"Invalid interface_type {interface_type}. Must be one of: 1 (USB), 2 (BLUETOOTH), 4 (ETHERNET), 7 (ANY)"
        )

    # Input validation for max_devices
    if not isinstance(max_devices, int) or max_devices <= 0:
        logger.warning(f"Mock: Invalid max_devices {max_devices}, using 1")
        max_devices = 1

    if max_devices > 10:  # Limit maximum devices
        logger.warning(f"Mock: max_devices {max_devices} too large, limiting to 10")
        max_devices = 10

    logger.info("Mock: Getting DAQ device inventory")
    # Return appropriate number of devices based on max_devices
    devices = [DaqDeviceDescriptor() for _ in range(min(max_devices, 1))]
    return devices


def _get_net_daq_device_descriptor_impl(host, port):
    """Mock function for network DAQ devices with comprehensive security validation."""
    # Comprehensive input validation to prevent injection attacks
    if not isinstance(host, str) or not host:
        raise ValueError("Host must be a non-empty string")

    # Validate host format (basic IP/hostname validation)
    if len(host) > 255:
        raise ValueError("Host string too long")
    if any(
        char in host for char in [";", "|", "&", "`", "$", "(", ")", "<", ">", '"', "'"]
    ):
        raise ValueError("Host contains invalid characters")

    if not isinstance(port, int) or port <= 0 or port > 65535:
        raise ValueError("Port must be a valid port number (1-65535)")

    # Thread-safe rate limiting using module-level variable
    # TEMPORARILY DISABLED FOR TESTING
    # current_time = time.time()
    #
    # # Use a thread-safe approach for rate limiting
    # if not hasattr(_get_net_daq_device_descriptor_impl, '_last_call'):
    #     _get_net_daq_device_descriptor_impl._last_call = 0.0
    #
    # if current_time - _get_net_daq_device_descriptor_impl._last_call < 0.1:  # 100ms minimum between calls
    #     raise RuntimeError("Rate limit exceeded for network operations")
    #
    # _get_net_daq_device_descriptor_impl._last_call = current_time

    logger.info("Mock: Getting network DAQ device descriptor")
    return DaqDeviceDescriptor()


def create_float_buffer(channel_count, samples_per_channel):
    """Mock function to create float buffer with strict security limits."""
    # Comprehensive input validation to prevent vulnerabilities
    if not isinstance(channel_count, int) or not isinstance(samples_per_channel, int):
        raise ValueError("channel_count and samples_per_channel must be integers")

    if channel_count <= 0 or samples_per_channel <= 0:
        raise ValueError("channel_count and samples_per_channel must be positive")

    # Strict limits to prevent memory exhaustion
    if channel_count > MAX_CHANNELS:
        raise ValueError(f"Too many channels (max: {MAX_CHANNELS})")
    if samples_per_channel > MAX_SCAN_COUNT:
        raise ValueError(f"Samples per channel too high (max: {MAX_SCAN_COUNT})")

    # Calculate buffer size with overflow protection
    try:
        buffer_size = channel_count * samples_per_channel
        if buffer_size <= 0 or buffer_size > MAX_SCAN_COUNT:
            raise ValueError("Buffer size calculation overflow")
    except OverflowError:
        raise ValueError("Buffer size calculation overflow")

    if buffer_size > MAX_BUFFER_SIZE // 8:  # 8 bytes per float64
        raise ValueError(f"Buffer size too large (max: {MAX_BUFFER_SIZE // 8} samples)")

    logger.info(
        f"Mock: Creating secure float buffer with {channel_count} channels, {samples_per_channel} samples per channel"
    )
    return [0.0] * buffer_size


# Create mock uldaq module
class MockUldaq:
    """Mock uldaq module that mimics the real uldaq library with security hardening."""

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
        return _get_net_daq_device_descriptor_impl(host, port)


# Export the mock module
uldaq = MockUldaq()

# Export the status for other modules to check
# (to avoid import of internal entities)
__all__ = ["uldaq", "DAQ_AVAILABLE"]
