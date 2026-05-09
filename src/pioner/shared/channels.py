"""Named constants for the AO/AI channel layout.

The wire format on the user-program JSON (``{"ch1": {...}}``), HDF5 group
keys (``voltage_profiles/ch1``), and the Tango pipe remains the literal
``"ch{N}"`` string. These constants are about naming and discoverability,
not type safety.

Channel layout matches ``spec.md`` section 1:

    AO ch0  shunt-path bias (~0.1 V)
    AO ch1  heater drive (DC + AC)
    AO ch2  guard heater / trigger
    AO ch3  spare

    AI ch0  heater current shunt
    AI ch1  Umod (high-gain thermopile)
    AI ch3  AD595 cold-junction
    AI ch4  Utpl (standard thermopile)
    AI ch5  heater voltage feedback
"""

from __future__ import annotations

from typing import Tuple

# ---------------------------------------------------------------------------
# AO channel keys (wire format: "chN" strings)
# ---------------------------------------------------------------------------
SHUNT_BIAS_AO: str = "ch0"
HEATER_AO: str = "ch1"
GUARD_AO: str = "ch2"
SPARE_AO: str = "ch3"

# ---------------------------------------------------------------------------
# AI channel indices (raw integers, used as DataFrame column labels)
# ---------------------------------------------------------------------------
HEATER_CURRENT_AI: int = 0
UMOD_AI: int = 1
AD595_AI: int = 3
UTPL_AI: int = 4
UHTR_AI: int = 5

#: Canonical AI subset retained by ``apply_calibration``. Order matters: it
#: matches what the post-processing code expects.
DEFAULT_AI_CHANNELS: Tuple[int, ...] = (
    HEATER_CURRENT_AI,
    UMOD_AI,
    AD595_AI,
    UTPL_AI,
    UHTR_AI,
)


# ---------------------------------------------------------------------------
# Wire-format helpers
# ---------------------------------------------------------------------------
def channel_key(index: int) -> str:
    """Return the wire-format name for an AO/AI channel index (``0 -> "ch0"``)."""
    if index < 0:
        raise ValueError(f"channel index must be non-negative, got {index}")
    return f"ch{index}"


def channel_index(key: str) -> int:
    """Inverse of :func:`channel_key` — extract the integer from ``"chN"``."""
    if not isinstance(key, str) or not key.startswith("ch"):
        raise ValueError(f"channel key must start with 'ch', got {key!r}")
    try:
        return int(key[2:])
    except ValueError as exc:
        raise ValueError(f"channel key {key!r} has no integer suffix") from exc


__all__ = [
    "SHUNT_BIAS_AO",
    "HEATER_AO",
    "GUARD_AO",
    "SPARE_AO",
    "HEATER_CURRENT_AI",
    "UMOD_AI",
    "AD595_AI",
    "UTPL_AI",
    "UHTR_AI",
    "DEFAULT_AI_CHANNELS",
    "channel_key",
    "channel_index",
]
