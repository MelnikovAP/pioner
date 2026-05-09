"""Connection management for the MCC DAQ board.

The handler is intentionally minimal: it discovers a single device on the
configured interface, connects/disconnects, and exposes child ``AiDevice`` and
``AoDevice`` handles. All higher-level logic lives in
:class:`pioner.back.experiment_manager.ExperimentManager`.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .mock_uldaq import DAQ_AVAILABLE, uldaq as ul

logger = logging.getLogger(__name__)


class DaqParams:
    """Parameters required to open a connection to the DAQ board."""

    def __init__(self) -> None:
        self.interface_type: int = ul.InterfaceType.ANY
        self.connection_code: int = -1
        # When True, AO and AI scans are armed with ``ScanOption.EXTTRIGGER``
        # and started by a single software trigger pulse so they share the
        # same DAQ clock edge. Eliminates the ~100 us start skew between AO
        # and AI on real hardware (todo P0-5). Default False until the
        # production DAQ is wired up — flipping it on without a trigger line
        # will hang the scans.
        self.hardware_trigger: bool = False

    def __str__(self) -> str:  # pragma: no cover - debug only
        return str(vars(self))


class DaqDeviceHandler:
    """Holder for a single ``uldaq.DaqDevice`` instance.

    Usage::

        with DaqDeviceHandler(params) as handler:
            handler.try_connect()
            ai = handler.get_ai_device()
            ...
    """

    def __init__(self, params: DaqParams):
        self._params = params
        self._daq_device = None
        self._init_daq_device()

    def _init_daq_device(self) -> None:
        if not DAQ_AVAILABLE:
            logger.warning(
                "Real uldaq is not available; the mock backend will be used."
            )
        devices = ul.get_daq_device_inventory(self._params.interface_type, 1)
        if not devices:
            raise RuntimeError("No DAQ devices found")
        self._daq_device = ul.DaqDevice(devices[0])

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "DaqDeviceHandler":
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.quit()

    # ------------------------------------------------------------------
    # Discovery / connection
    # ------------------------------------------------------------------
    def get_descriptor(self):
        return self._daq_device.get_descriptor()

    def is_connected(self) -> bool:
        return self._daq_device.is_connected()

    def connect(self) -> None:
        descriptor = self.get_descriptor()
        logger.info("Connecting to %s", descriptor.dev_string)
        self._daq_device.connect(connection_code=self._params.connection_code)
        if self.is_connected():
            logger.info("DAQ device connected")
        else:
            logger.warning("DAQ device failed to connect")

    def try_connect(self, timeout: int = 60, sleep_time: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_connected():
                try:
                    self.connect()
                except Exception as exc:
                    logger.debug("Connect attempt failed: %s", exc)
            if self.is_connected():
                return
            time.sleep(sleep_time)
        raise TimeoutError("DAQ device connection timed out")

    def disconnect(self) -> None:
        try:
            self._daq_device.disconnect()
        finally:
            logger.info("DAQ device disconnected")

    def release(self) -> None:
        try:
            self._daq_device.release()
        finally:
            logger.info("DAQ device released")

    def reset(self) -> None:
        self._daq_device.reset()
        logger.info("DAQ device reset")

    def quit(self) -> None:
        if self.is_connected():
            self.disconnect()
        self.release()

    # ------------------------------------------------------------------
    # Sub-device access
    # ------------------------------------------------------------------
    def get(self):
        return self._daq_device

    def get_ai_device(self):
        return self._daq_device.get_ai_device()

    def get_ao_device(self):
        return self._daq_device.get_ao_device()

    # ------------------------------------------------------------------
    # Hardware-trigger primitive (todo P0-5)
    # ------------------------------------------------------------------
    def fire_software_trigger(self) -> None:
        """Pulse the DAQ trigger line so both EXTTRIGGER-armed scans start.

        On real hardware this drives a digital output (typically wired
        externally to the board's trigger input pin) for one clock cycle. The
        mock backend implements this as a synchronised release of the AO and
        AI workers.
        """
        fire = getattr(self._daq_device, "fire_software_trigger", None)
        if fire is None:
            raise RuntimeError(
                "DAQ backend does not expose a software-trigger primitive; "
                "hardware_trigger=True requires either an external pulse "
                "generator or a DIO line wired to the trigger input."
            )
        fire()
