"""AC modulation utilities for slow / iso calorimetry modes.

For microgram samples the DC heat-capacity signal is buried in the noise of
the analog front-end. The standard workaround is to superimpose a small
sinusoidal modulation on the DC heating profile and recover the heat capacity
from the AC component using a lock-in detection in software:

* AO output:    ``U(t) = U_DC(t) + A * sin(2*pi*f*t)``
* AI temperature: ``T(t) = T_DC(t) + dT_AC * sin(2*pi*f*t - phi)``
* Heat capacity ``C_p(T) ~ P_AC / (omega * dT_AC) * cos(phi)``

This module only deals with the *signal-processing* part:

* :class:`ModulationParams` — small dataclass for ``frequency``,
  ``amplitude``, and ``offset``.
* :func:`apply_modulation`  — superimpose AC on a base voltage profile.
* :func:`lockin_demodulate` — single-frequency software lock-in returning
  amplitude and phase of an AI channel.

Time vectors are expressed in **seconds**. Voltage is in **volts**.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

try:
    from scipy.signal import butter, sosfiltfilt
    _HAVE_SCIPY = True
except ImportError:  # pragma: no cover - scipy should always be present
    _HAVE_SCIPY = False


@dataclass(frozen=True)
class ModulationParams:
    """AC modulation parameters loaded from settings.json."""

    frequency: float = 0.0  # Hz
    amplitude: float = 0.0  # V (peak)
    offset: float = 0.0     # V (DC bias added on top of the base profile)

    @property
    def enabled(self) -> bool:
        """``True`` if either amplitude or offset is non-zero."""
        return self.amplitude > 0.0 or self.offset != 0.0

    @property
    def lockin_capable(self) -> bool:
        """Lock-in demodulation needs both a positive frequency and amplitude."""
        return self.amplitude > 0.0 and self.frequency > 0.0

    def with_amplitude(self, amplitude: float) -> "ModulationParams":
        return ModulationParams(self.frequency, amplitude, self.offset)


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------
def apply_modulation(
    time_s: np.ndarray,
    base_voltage: np.ndarray,
    params: ModulationParams,
) -> np.ndarray:
    """Add AC modulation (and a DC offset) to a DC voltage profile.

    Parameters
    ----------
    time_s
        Time axis in seconds, same length as ``base_voltage``.
    base_voltage
        DC voltage profile in volts.
    params
        Modulation parameters.

    Returns
    -------
    np.ndarray
        Modulated voltage profile, ``base_voltage + offset + A * sin(2*pi*f*t)``.
    """
    time_s = np.asarray(time_s, dtype=float)
    base_voltage = np.asarray(base_voltage, dtype=float)
    if time_s.shape != base_voltage.shape:
        raise ValueError("time_s and base_voltage must have the same shape")

    if not params.enabled:
        return base_voltage.copy()

    ac = params.amplitude * np.sin(2.0 * np.pi * params.frequency * time_s)
    return base_voltage + params.offset + ac


# ---------------------------------------------------------------------------
# Lock-in detection
# ---------------------------------------------------------------------------
def lockin_demodulate(
    signal: np.ndarray,
    sample_rate: float,
    frequency: float,
    bandwidth: float | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Single-frequency software lock-in.

    Multiplies ``signal`` by ``sin`` and ``cos`` references at ``frequency``
    and applies a moving-average low-pass filter with the given ``bandwidth``
    (in Hz). The returned amplitude and phase have the same length as the
    input signal.

    Parameters
    ----------
    signal
        AI samples.
    sample_rate
        Sampling rate of ``signal`` in Hz.
    frequency
        Reference frequency (modulation frequency) in Hz.
    bandwidth
        Low-pass cut-off of the moving average. Defaults to ``frequency / 5``,
        which is a common rule of thumb (it suppresses the 2*f component while
        keeping settling time short).

    Returns
    -------
    (amplitude, phase)
        ``amplitude`` is the AC amplitude of ``signal`` at ``frequency`` (same
        units as ``signal``); ``phase`` is the phase lag in radians.
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("signal must be 1-D")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    if bandwidth is None:
        bandwidth = frequency / 5.0
    if bandwidth <= 0:
        raise ValueError("bandwidth must be positive")
    if bandwidth >= sample_rate / 2.0:
        raise ValueError("bandwidth must be below Nyquist")

    n = signal.size
    t = np.arange(n) / sample_rate
    omega = 2.0 * np.pi * frequency
    sin_ref = np.sin(omega * t)
    cos_ref = np.cos(omega * t)

    in_phase = signal * sin_ref
    quadrature = signal * cos_ref

    if _HAVE_SCIPY:
        # 4th-order Butterworth low-pass, applied with sosfiltfilt for zero
        # phase-lag. This is what bench-top lock-in amplifiers do.
        sos = butter(N=4, Wn=bandwidth / (sample_rate / 2.0), btype="low", output="sos")
        # ``sosfiltfilt`` has a minimum signal-length requirement; for tiny
        # signals fall back to the moving-average path.
        if signal.size > 4 * 4 * 3:  # ≥ 4*order*3
            in_phase_lp = sosfiltfilt(sos, in_phase)
            quadrature_lp = sosfiltfilt(sos, quadrature)
        else:
            in_phase_lp, quadrature_lp = _moving_average_demod(in_phase, quadrature, sample_rate, frequency, bandwidth)
    else:
        in_phase_lp, quadrature_lp = _moving_average_demod(in_phase, quadrature, sample_rate, frequency, bandwidth)

    # Lock-in convention: signal = A * sin(omega*t - phi), phi = phase lag.
    # I_lp = A/2 * cos(phi); Q_lp = -A/2 * sin(phi). The phase lag is therefore
    # ``-arctan2(Q, I)`` so that a positive value means the signal trails the
    # reference (which is what physicists expect).
    amplitude = 2.0 * np.sqrt(in_phase_lp**2 + quadrature_lp**2)
    phase = -np.arctan2(quadrature_lp, in_phase_lp)
    return amplitude, phase


def _moving_average_demod(in_phase, quadrature, sample_rate, frequency, bandwidth):
    """Fallback low-pass when scipy is not available."""
    samples_per_period = max(1, int(round(sample_rate / frequency)))
    win_len = max(samples_per_period, int(round(sample_rate / bandwidth)))
    win_len = max(samples_per_period, samples_per_period * round(win_len / samples_per_period))
    kernel = np.ones(win_len, dtype=float) / win_len
    return _convolve_same(in_phase, kernel), _convolve_same(quadrature, kernel)


def _convolve_same(signal: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """``np.convolve(... mode='same')`` but more robust at the boundaries.

    We pad the input by replicating the boundary values so the moving average
    does not bleed zeros into the result, which would otherwise distort the
    lock-in amplitude near the edges.
    """
    pad = kernel.size // 2
    if pad == 0:
        return signal.copy()
    padded = np.concatenate([
        np.full(pad, signal[0]),
        signal,
        np.full(pad, signal[-1]),
    ])
    return np.convolve(padded, kernel, mode="valid")[: signal.size]


__all__ = [
    "ModulationParams",
    "apply_modulation",
    "lockin_demodulate",
]
