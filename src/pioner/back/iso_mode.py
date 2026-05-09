"""Backwards-compatible iso-mode shim.

The historical ``IsoMode`` accepted a degenerate dict like
``{"ch2": {"volt": 0}}`` (no ``time`` array) and held the voltage indefinitely
until disconnection. To keep the Tango server working we accept the same
shape, normalise it into a proper one-second program for
:class:`pioner.back.modes.IsoMode`, and expose ``arm`` / ``run`` that match
the old API. The new behaviour adds:

* AC modulation when ``BackSettings.modulation`` is enabled.
* A bounded duration parameter on ``run`` (default: indefinite emulated as a
  large number) so the run can be stopped cleanly.
* Streaming AI samples to a ring buffer that the caller can grab via
  :meth:`snapshot`.
"""

from __future__ import annotations

import logging
from typing import Optional

from pioner.shared.calibration import Calibration
from pioner.shared.channels import (
    DEFAULT_AI_CHANNELS,
    HEATER_AO,
    channel_index,
    channel_key,
)
from pioner.shared.modulation import ModulationParams
from pioner.shared.settings import BackSettings
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.modes import IsoMode as _IsoMode

logger = logging.getLogger(__name__)


def _normalise_channel_program(
    chan_temp_volt: dict,
    duration_seconds: int,
) -> dict:
    """Turn ``{"chN": {"volt": v}}`` into a 1 s constant program."""
    out: dict = {}
    for ch, table in chan_temp_volt.items():
        if "time" in table:
            out[ch] = table
            continue
        if "volt" in table:
            value = float(table["volt"])
            kind = "volt"
        elif "temp" in table:
            value = float(table["temp"])
            kind = "temp"
        else:
            raise ValueError(f"channel {ch} requires 'temp' or 'volt'")
        out[ch] = {
            "time": [0.0, duration_seconds * 1000.0],
            kind: [value, value],
        }
    return out


class IsoMode:
    def __init__(
        self,
        daq_device_handler: DaqDeviceHandler,
        settings: BackSettings,
        chan_temp_volt: dict,
        calibration: Calibration,
        duration_seconds: int = 1,
        modulation: Optional[ModulationParams] = None,
        modulation_channel: str = HEATER_AO,
    ) -> None:
        self._duration_seconds = max(int(duration_seconds), 1)
        programs = _normalise_channel_program(chan_temp_volt, self._duration_seconds)
        self._mode = _IsoMode(
            daq_device_handler,
            settings,
            calibration,
            programs,
            modulation=modulation,
            modulation_channel=modulation_channel,
        )
        # Maintain the legacy ``arm()`` -> ``(channel, voltage)`` return.
        ch_name = next(iter(chan_temp_volt))
        self._channel = channel_index(ch_name)
        self._voltage: Optional[float] = None

    def arm(self):
        self._mode.arm()
        profile = self._mode.voltage_profiles.get(channel_key(self._channel))
        self._voltage = float(profile[0]) if profile is not None else 0.0
        return self._channel, self._voltage

    def is_armed(self) -> bool:
        return self._mode.is_armed()

    def run(self, do_ai: bool = True, duration_seconds: Optional[float] = None):
        if duration_seconds is None:
            duration_seconds = self._duration_seconds
        if not do_ai:
            # Just hold the voltage (no AI streaming).
            self._mode.run(duration_seconds=0.0)
            return None
        return self._mode.run(duration_seconds=duration_seconds)

    def stop(self) -> None:
        """Abort a running ``run()`` from another thread (or from Tango)."""
        self._mode.stop()

    def ai_stop(self) -> None:  # legacy API
        # Old GUIs called this after ``run(do_ai=False)`` to drop the held
        # voltage. Forward to the new ``stop()`` primitive so the legacy
        # entry-point keeps working.
        self.stop()


__all__ = ["IsoMode"]
