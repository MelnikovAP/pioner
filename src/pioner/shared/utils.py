"""Shared utilities for the pioner package.

Contains:
* Numeric helpers (``is_int``, ``list_bitwise_or``).
* Calibration converters between heater voltage and temperature.
* Lightweight ``Dict2Class`` adapter used by the front-end.

The temperature/voltage converters are vectorised with numpy so they handle
million-point profiles without measurable overhead. They also clamp inputs
into the calibrated range to avoid silent out-of-bounds indexing.
"""

from __future__ import annotations

from typing import Iterable, List

import numpy as np

from pioner.shared.calibration import Calibration


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------
def is_int(key) -> bool:
    """Return ``True`` if ``key`` is an integer or a string containing one."""
    if isinstance(key, bool):
        return False  # bool is a subtype of int but we never want it here.
    if isinstance(key, int):
        return True
    if isinstance(key, str):
        # Allow optional leading sign, e.g. "-1".
        return key.lstrip("+-").isdigit()
    return False


def is_int_or_raise(key) -> bool:
    """Same as :func:`is_int` but raises ``ValueError`` if not an integer."""
    if is_int(key):
        return True
    raise ValueError(f"'{key}' is not an integer value.")


def list_bitwise_or(ints: Iterable[int]) -> int:
    """Bitwise OR over an iterable of integers (used for uldaq flag fields)."""
    res = 0
    for i in ints:
        res |= int(i)
    return res


# ---------------------------------------------------------------------------
# Calibration converters
# ---------------------------------------------------------------------------
def voltage_to_temperature(voltage: np.ndarray, calibration: Calibration) -> np.ndarray:
    """Convert heater voltage to temperature using a 3rd-order polynomial.

    The polynomial coefficients ``theater0..theater2`` come from the chip
    calibration. Voltages outside ``[0, safe_voltage]`` are clamped before the
    polynomial is evaluated.
    """
    volt = np.asarray(voltage, dtype=float).copy()
    np.clip(volt, 0.0, calibration.safe_voltage, out=volt)
    return (
        calibration.theater0 * volt
        + calibration.theater1 * volt**2
        + calibration.theater2 * volt**3
    )


def temperature_to_voltage(
    temp: np.ndarray | List[float],
    calibration: Calibration,
    resolution: float = 1e-4,
) -> np.ndarray:
    """Invert :func:`voltage_to_temperature` numerically.

    Builds a fine voltage grid over ``[0, safe_voltage]``, evaluates
    temperature on that grid and uses ``np.searchsorted`` to find the lowest
    voltage that produces the requested temperature.

    Real chip calibration polynomials (e.g. ``-2.425*V + 8.04*V² - 0.43*V³``)
    are *almost* monotonic on ``[0, safe_voltage]`` but can have a small
    sub-zero dip near ``V = 0`` where the cubic term wins over the linear one.
    We tolerate that by walking on a monotonized version of the temperature
    grid (``np.maximum.accumulate``) — physically the heater can only heat,
    so requesting ``T < T(V=0)`` always maps to ``V = 0``. We still reject
    grossly non-monotonic curves where the *overall* trend is decreasing.
    """
    temp = np.asarray(temp, dtype=float)
    if temp.size == 0:
        return np.zeros(0, dtype=float)

    # TODO(physical): when calibrators commit a new ``Theater`` polynomial,
    # explicitly verify that ``dT/dV > 0`` on ``[0, safe_voltage]``. The
    # historical 39392 sensor polynomial has a small sub-zero dip near V≈0.16
    # which we tolerate via ``cumulative max`` below; coefficient drift can
    # widen that dip and silently bias the inversion.
    n_grid = max(int(round(calibration.safe_voltage / resolution)), 1024)
    volt_calib = np.linspace(0.0, calibration.safe_voltage, n_grid)
    temp_calib = voltage_to_temperature(volt_calib, calibration)

    # Reject only catastrophic non-monotonicity (overall trend has to be up,
    # i.e. ``T(V_max) > T(V=0)`` by a meaningful margin).
    if temp_calib[-1] - temp_calib[0] <= 1e-3:
        raise ValueError(
            "Calibration polynomial is not monotonic on [0, safe_voltage]; "
            "temperature -> voltage inversion is ambiguous."
        )

    # Force a non-decreasing curve so ``searchsorted`` is well-defined even if
    # the raw polynomial dips slightly below T(V=0) somewhere on the interval.
    temp_mono = np.maximum.accumulate(temp_calib)

    temp_clipped = np.clip(temp, calibration.min_temp, calibration.max_temp)
    idx = np.searchsorted(temp_mono, temp_clipped, side="left")
    np.clip(idx, 0, n_grid - 1, out=idx)
    return np.round(volt_calib[idx], 4)


# ---------------------------------------------------------------------------
# Misc adapter used by the front-end
# ---------------------------------------------------------------------------
class Dict2Class:
    """Wrap a dictionary so its keys are accessible as attributes."""

    def __init__(self, my_dict: dict):
        for key, value in my_dict.items():
            setattr(self, key, value)
        self.my_dict = dict(my_dict)

    def get_dict(self) -> dict:
        return self.my_dict


if __name__ == "__main__":
    # Quick self-check used during development.
    from time import time

    cal = Calibration()
    temp_exp = np.concatenate([
        np.zeros(1000) - 1.0,
        np.linspace(-1.0, 300.0, 3000),
        np.ones(1000) + 299.0,
        np.linspace(300.0, -2.0, 3000),
        np.zeros(1000) - 2.0,
    ])

    t0 = time()
    volt_exp = temperature_to_voltage(temp_exp, cal)
    print(f"vectorised T->V on {temp_exp.size} points: {(time() - t0) * 1e3:.2f} ms")
    print("first 10 voltages:", volt_exp[:10])
