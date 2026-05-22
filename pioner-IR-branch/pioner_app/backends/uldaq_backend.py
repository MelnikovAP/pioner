import logging

from pioner_app.core.settings import settings
from pioner_app.backends.base import HardwareBackend


logger = logging.getLogger(__name__)


class UldaqHardwareBackend(HardwareBackend):
    backend_name = "direct"

    def __init__(self):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.device = None
        self.ai_device = None
        self.ao_device = None
        self.descriptor = None
        self.device_name = "ULDAQ"

    def connect(self):
        """?????????? ?????? `connect`."""
        try:
            from uldaq import DaqDevice, InterfaceType, get_daq_device_inventory
        except Exception as exc:
            raise RuntimeError(
                "Direct ULDAQ backend is unavailable in this Python environment. "
                "Run the app inside WSL/Linux with libuldaq installed, or switch to Tango."
            ) from exc

        logger.info("Searching for DAQ devices via ULDAQ")
        interface = InterfaceType(settings.interface_type[0])
        devices = get_daq_device_inventory(interface)
        if len(devices) == 0:
            raise RuntimeError("DAQ device not found")

        self.descriptor = devices[0]
        self.device_name = getattr(self.descriptor, "product_name", "ULDAQ")
        self.device = DaqDevice(self.descriptor)
        self.device.connect()
        self.ai_device = self.device.get_ai_device()
        self.ao_device = self.device.get_ao_device()

    def get_ai_device(self):
        """?????????? ?????? `get_ai_device`."""
        if self.ai_device is None:
            raise RuntimeError("AI device not available")
        return self.ai_device

    def get_ao_device(self):
        """?????????? ?????? `get_ao_device`."""
        if self.ao_device is None:
            raise RuntimeError("AO device not available")
        return self.ao_device

    def disconnect(self):
        """????????? ?????? `disconnect`."""
        if self.device is None:
            return
        try:
            if self.device.is_connected():
                self.device.disconnect()
        finally:
            self.device.release()
            self.device = None
            self.ai_device = None
            self.ao_device = None
