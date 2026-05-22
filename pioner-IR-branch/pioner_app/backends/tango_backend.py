import logging

from pioner_app.core.settings import settings
from pioner_app.backends.base import HardwareBackend


logger = logging.getLogger(__name__)


class TangoHardwareBackend(HardwareBackend):
    backend_name = "tango"

    def __init__(self):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.proxy = None
        self.descriptor = None
        self.device_name = "Tango Controls"
        self.tango_host = getattr(settings, "tango_host", "")
        self.device_proxy = getattr(settings, "device_proxy", "")

    def connect(self):
        """?????????? ?????? `connect`."""
        if not self.device_proxy:
            raise RuntimeError("Tango backend is configured, but 'Device proxy' is empty in config.json")

        try:
            import tango
        except ImportError as exc:
            raise RuntimeError("Tango backend requires the tango package to be installed") from exc

        logger.info("Preparing Tango Controls connection to %s", self.device_proxy)
        self.proxy = tango.DeviceProxy(self.device_proxy)
        if self.tango_host:
            self.proxy.set_timeout_millis(5000)
        raise NotImplementedError(
            "Tango backend scaffold is ready, but mapping Tango device commands/attributes to AI/AO interfaces is not implemented yet."
        )

    def get_ai_device(self):
        """?????????? ?????? `get_ai_device`."""
        raise NotImplementedError("Tango AI adapter is not implemented yet")

    def get_ao_device(self):
        """?????????? ?????? `get_ao_device`."""
        raise NotImplementedError("Tango AO adapter is not implemented yet")

    def disconnect(self):
        """????????? ?????? `disconnect`."""
        self.proxy = None
