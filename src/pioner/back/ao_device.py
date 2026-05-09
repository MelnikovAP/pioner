"""Thin wrapper over ``uldaq.AoDevice``."""

from __future__ import annotations

import logging
from typing import List, Tuple

from .mock_uldaq import uldaq as ul

logger = logging.getLogger(__name__)


# Hardware DAC range_id -> peak |V| accepted by the converter. Mirrors the
# uldaq ``Range`` enum (BIPxxVOLTS family). Used as a sanity guard in
# :meth:`AoDeviceHandler.set_voltage` and ``scan`` so a programmer error that
# bypasses the chip-specific ``safe_voltage`` clamp (e.g. ``em.ao_set(1, 50)``)
# fails loudly instead of silently saturating the DAC on real hardware.
_RANGE_MAX_VOLTAGE = {
    0: 60.0,   # BIP60VOLTS
    1: 30.0,   # BIP30VOLTS
    2: 20.0,   # BIP20VOLTS
    3: 15.0,   # BIP15VOLTS
    5: 10.0,   # BIP10VOLTS
}


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
        max_v = _RANGE_MAX_VOLTAGE.get(self._params.range_id)
        if max_v is not None and ao_buffer:
            peak = max(abs(float(v)) for v in ao_buffer)
            if peak > max_v:
                raise ValueError(
                    f"AO buffer peak |V|={peak:.3f} V exceeds the configured "
                    f"analog range (range_id={self._params.range_id}, "
                    f"+/-{max_v} V). Clamp the profile to safe_voltage upstream."
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

        ``voltage`` is checked against the configured analog range (``range_id``)
        so a caller that bypassed the chip-specific ``safe_voltage`` clamp gets
        a loud ``ValueError`` rather than silently saturating the DAC. The chip
        safe envelope is enforced upstream by ``modes._program_to_voltage``.
        """
        scan_status, _ = self.status()
        if scan_status == ul.ScanStatus.RUNNING:
            self.stop()

        voltage = float(voltage)
        max_v = _RANGE_MAX_VOLTAGE.get(self._params.range_id)
        if max_v is not None and abs(voltage) > max_v:
            raise ValueError(
                f"AO voltage {voltage:+.3f} V exceeds the configured analog "
                f"range (range_id={self._params.range_id}, +/-{max_v} V). "
                "The caller must clamp to the chip-specific safe_voltage."
            )

        analog_range = ul.Range(self._params.range_id)
        return self._ao_device.a_out(
            ao_channel,
            analog_range,
            self._params.scan_flags,
            voltage,
        )
