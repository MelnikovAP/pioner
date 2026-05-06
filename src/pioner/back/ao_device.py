"""Thin wrapper over ``uldaq.AoDevice``."""

from __future__ import annotations

import logging
from typing import List, Tuple

from .mock_uldaq import uldaq as ul

logger = logging.getLogger(__name__)


class AoParams:
    """Mutable bag of analog-output parameters parsed from JSON or set manually."""

    def __init__(self) -> None:
        self.sample_rate: int = -1
        self.range_id: int = -1
        self.low_channel: int = -1
        self.high_channel: int = -1
        self.scan_flags: int = ul.AOutScanFlag.DEFAULT
        self.options: int = ul.ScanOption.CONTINUOUS

    def __str__(self) -> str:  # pragma: no cover - debug only
        return str(vars(self))

    def channel_count(self) -> int:
        return self.high_channel - self.low_channel + 1


class AoDeviceHandler:
    """Wrap an ``uldaq.AoDevice``.

    The historical class assumed AO is always paced with a profile. For iso
    mode we also need to set a single static voltage on a channel — that path
    is handled by :meth:`set_voltage`.
    """

    def __init__(self, ao_device, params: AoParams):
        if ao_device is None:
            raise RuntimeError("DAQ device does not expose an AoDevice")

        info = ao_device.get_info()
        if not info.has_pacer():
            raise RuntimeError("AoDevice does not support hardware pacing")

        self._ao_device = ao_device
        self._params = params

    def get(self):
        return self._ao_device

    def stop(self) -> None:
        try:
            self._ao_device.scan_stop()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("AO scan_stop failed: %s", exc)

    def status(self) -> Tuple[int, "object"]:
        return self._ao_device.get_scan_status()

    def scan(self, ao_buffer: List[float]) -> float:
        """Start an analog-output scan with the provided buffer."""
        n_chans = self._params.channel_count()
        if n_chans <= 0:
            raise ValueError("AO channel range is invalid")
        if len(ao_buffer) % n_chans != 0:
            raise ValueError(
                f"AO buffer length {len(ao_buffer)} is not divisible by "
                f"the number of channels ({n_chans})"
            )
        samples_per_channel = len(ao_buffer) // n_chans
        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out_scan(
            self._params.low_channel,
            self._params.high_channel,
            analog_range,
            samples_per_channel,
            self._params.sample_rate,
            self._params.options,
            self._params.scan_flags,
            ao_buffer,
        )

    def set_voltage(self, ao_channel: int, voltage: float) -> float:
        """Hold ``voltage`` on a single AO channel until the device is released.

        This is the iso-mode primitive. It tolerates being called while a scan
        is running by stopping the scan first (otherwise ``a_out`` may fail).
        """
        scan_status, _ = self.status()
        if scan_status == ul.ScanStatus.RUNNING:
            self.stop()

        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out(
            ao_channel,
            analog_range,
            self._params.scan_flags,
            float(voltage),
        )
