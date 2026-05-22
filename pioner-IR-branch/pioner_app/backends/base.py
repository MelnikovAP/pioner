from abc import ABC, abstractmethod


class HardwareBackend(ABC):
    """Common backend contract for hardware transports."""

    backend_name = "base"
    descriptor = None
    device_name = "Unknown backend"

    @abstractmethod
    def connect(self):
        """?????????? ?????? `connect`."""
        raise NotImplementedError

    @abstractmethod
    def get_ai_device(self):
        """?????????? ?????? `get_ai_device`."""
        raise NotImplementedError

    @abstractmethod
    def get_ao_device(self):
        """?????????? ?????? `get_ao_device`."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self):
        """????????? ?????? `disconnect`."""
        raise NotImplementedError
