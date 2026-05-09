"""AC modulation utilities for slow / iso calorimetry modes.

For microgram samples the DC heat-capacity signal is buried in the noise of
the analog front-end. The standard workaround is to superimpose a small
sinusoidal modulation on the DC heating profile and recover the heat capacity
from the AC component using a lock-in detection in software:

* AO output:    ``U(t) = U_DC(t) + A * sin(2*pi*f*t)``
* AI temperature: ``T(t) = T_DC(t) + dT_AC * sin(2*pi*f*t - phi)``
* Heat capacity ``C_p(T) ~ P_AC / (omega * dT_AC) * cos(phi)``

This module deals with the *signal-processing* part:

* :class:`ModulationParams` -- small dataclass for ``frequency``,
  ``amplitude``, and ``offset``.
* :func:`apply_modulation`  -- superimpose AC on a base voltage profile.
* :func:`lockin_demodulate` -- single-frequency software lock-in (time-
  domain, sin/cos demod + Butterworth LP) returning a per-sample amplitude
  and phase trace. Used by SlowMode where the DC component varies in time.
* :func:`fft_demodulate`    -- single-shot FFT-based demodulator returning
  *scalar* amplitude and phase at the fundamental and at user-selected
  harmonics (default 1f/2f/3f), plus a spectral-leakage diagnostic. Used
  by IsoMode where the response is stationary, so a global FFT is the
  natural estimator and bonus harmonics come for free (relevant in AC
  calorimetry: 2f probes nonlinearities of C_p, 3f gives a sanity check
  on harmonic distortion of the heater drive).
* :func:`check_ao_period_integrity` -- verify that an AO modulation buffer
  intended for CONTINUOUS replay wraps without a phase discontinuity.
  Required because IsoMode plays the AO buffer indefinitely; if the
  buffer length is not an integer number of AC cycles, every wrap injects
  a phase jump that contaminates both the chip drive and the recovered
  C_p amplitude/phase.

Time vectors are expressed in **seconds**. Voltage is in **volts**.

Phase convention (used by both demodulators)
--------------------------------------------
The reference is ``sin(2*pi*f*t)``. A signal modelled as
``A * sin(2*pi*f*t - phi)`` has phase lag ``phi``: positive ``phi`` means
the signal trails the reference (physically natural for a sample whose
temperature response lags the heater drive). Phase is wrapped to
``[-pi, pi]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Tuple

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


# ---------------------------------------------------------------------------
# FFT-based demodulation (IsoMode, stationary response)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HarmonicAmplitude:
    """Amplitude and phase at one harmonic of the modulation frequency."""

    harmonic: int       # 1 = fundamental (f), 2 = 2f, 3 = 3f, ...
    amplitude: float    # peak amplitude, same units as the input signal
    phase: float        # rad, in [-pi, pi], lock-in phase-lag convention


@dataclass(frozen=True)
class FFTDemodResult:
    """Output of :func:`fft_demodulate`. ``window_samples`` is the length of
    the integer-cycle slice actually fed to the FFT (the leading samples of
    the input are dropped if the full length is not an integer number of
    AC periods, so the bins fall exactly on the harmonics)."""

    harmonics: Tuple[HarmonicAmplitude, ...]
    leakage_fraction: float    # 1 - sum(harmonic_power) / total_AC_power
    window_samples: int

    @property
    def fundamental(self) -> HarmonicAmplitude:
        """Convenience accessor for the 1f harmonic (raises if not requested)."""
        for h in self.harmonics:
            if h.harmonic == 1:
                return h
        raise KeyError("fundamental (1f) was not requested")


def _integer_cycle_length(
    n_total: int, sample_rate: float, frequency: float
) -> int:
    """Return the largest ``N <= n_total`` such that ``N * f / fs`` is an
    *exact* integer, i.e. ``N`` samples cover an integer number of AC cycles
    and the requested frequency falls on a single FFT bin (no leakage).

    For "nice" frequencies (e.g. ``f=37.5 Hz`` at ``fs=20 kHz``) this picks a
    sub-second window that aligns perfectly with the FFT grid. For
    irrational ratios we fall back to ``n_total`` and accept a small leakage
    -- the calling FFT path still works, just with a slightly wider effective
    line shape.
    """
    if n_total <= 0:
        return 0
    # Express f / fs as a reduced fraction p/q. The smallest integer-cycle
    # window length is then ``q``; we round n_total down to the nearest
    # multiple of q.
    ratio = (
        Fraction(frequency).limit_denominator(10**6)
        / Fraction(sample_rate).limit_denominator(10**6)
    )
    q = ratio.denominator
    if q == 0 or q > n_total:
        return int(n_total)
    return int((n_total // q) * q)


def fft_demodulate(
    signal: np.ndarray,
    sample_rate: float,
    frequency: float,
    harmonics: Iterable[int] = (1, 2, 3),
) -> FFTDemodResult:
    """FFT-based demodulator for stationary AC response (IsoMode).

    The function picks an integer-cycle window of the input, computes a real
    FFT, and reads the amplitude/phase directly from the harmonic bins. With
    the integer-cycle window the bins fall exactly on the harmonics so there
    is no need for any window function -- a rectangular window gives the
    cleanest line-shape and the simplest physical interpretation.

    Parameters
    ----------
    signal
        AI samples (1-D). Should be long enough to contain at least one
        modulation period at ``frequency``.
    sample_rate
        Sampling rate of ``signal`` in Hz.
    frequency
        Modulation frequency (the fundamental) in Hz; must be below Nyquist.
    harmonics
        Multiples of the fundamental to extract. Higher-than-Nyquist
        harmonics return ``NaN`` for both amplitude and phase.

    Returns
    -------
    FFTDemodResult
        Per-harmonic ``(amplitude, phase)`` plus a leakage fraction
        diagnostic (fraction of total AC power *not* concentrated at the
        requested harmonics).

    Notes
    -----
    Conversion from FFT bin to lock-in (A, phi):

    With ``s(t) = A * sin(2*pi*f*t - phi)`` and the numpy forward FFT
    convention ``X[k] = sum_n s[n] exp(-2j*pi*k*n/N)``, the analytical FFT
    over an integer number of cycles gives
    ``X[k_f] = -j * (A * N / 2) * exp(-j*phi)``.
    Therefore ``A = 2 * |X[k_f]| / N`` and
    ``phi = -pi/2 - arg(X[k_f])`` (then wrapped to ``[-pi, pi]``).
    """
    signal = np.asarray(signal, dtype=float)
    if signal.ndim != 1:
        raise ValueError("signal must be 1-D")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    if frequency >= sample_rate / 2.0:
        raise ValueError("frequency must be below Nyquist (sample_rate / 2)")

    samples_per_period = sample_rate / frequency
    if signal.size < int(np.ceil(samples_per_period)):
        raise ValueError(
            f"signal too short for one modulation period "
            f"(have {signal.size} samples, need >= {int(np.ceil(samples_per_period))})"
        )

    n = _integer_cycle_length(signal.size, sample_rate, frequency)
    if n < int(np.ceil(samples_per_period)):
        # No integer-cycle slice fits in the signal; fall back to the whole
        # input. Leakage will be non-trivial but still a useful estimate.
        n = signal.size
    # Use the *trailing* slice: in IsoMode the leading samples are the most
    # likely to contain a thermal start-up transient. We compensate for the
    # window offset below so the recovered phase still matches the lock-in
    # convention (referenced to sample 0 of the original input).
    start_index = signal.size - n
    s = signal[start_index:].astype(float, copy=True)
    s -= s.mean()  # drop DC so the harmonic bins dominate the leakage metric

    spectrum = np.fft.rfft(s)
    cycles_in_window = int(round(n * frequency / sample_rate))
    # Phase shift to map "phi referenced to window start" back to
    # "phi referenced to original t=0". Each harmonic h experiences a shift
    # of ``h * omega * t_start``.
    omega_t_start = 2.0 * np.pi * frequency * start_index / sample_rate

    harmonic_results = []
    harmonic_power = 0.0
    seen = set()
    for h in harmonics:
        if h <= 0:
            raise ValueError(f"harmonic must be a positive integer, got {h}")
        if h in seen:
            continue
        seen.add(h)
        bin_idx = h * cycles_in_window
        if bin_idx >= spectrum.size:
            # h*f >= Nyquist -> aliased / unobservable. Report NaN.
            harmonic_results.append(HarmonicAmplitude(h, float("nan"), float("nan")))
            continue
        x = spectrum[bin_idx]
        amp = 2.0 * abs(x) / n
        phase_window = -np.pi / 2.0 - np.angle(x)
        phase = phase_window + h * omega_t_start
        # wrap to (-pi, pi]
        phase = (phase + np.pi) % (2 * np.pi) - np.pi
        harmonic_results.append(HarmonicAmplitude(h, float(amp), float(phase)))
        harmonic_power += float(abs(x)) ** 2

    # Total AC power (DC bin already removed by mean-subtraction above).
    # Parseval normalisation cancels out in the ratio.
    total_power = float(np.sum(np.abs(spectrum) ** 2))
    leakage = 1.0 - harmonic_power / total_power if total_power > 0 else 0.0
    # Numerical guard: tiny negative values from float roundoff are rounded
    # to 0; capping at 1.0 is defensive against pathological inputs.
    leakage = float(min(max(leakage, 0.0), 1.0))

    return FFTDemodResult(
        harmonics=tuple(harmonic_results),
        leakage_fraction=leakage,
        window_samples=int(n),
    )


# ---------------------------------------------------------------------------
# AO modulation buffer integrity (IsoMode CONTINUOUS replay)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AOPeriodReport:
    """Diagnostic for an AO modulation buffer about to be played CONTINUOUS.

    Physical interpretation
    -----------------------
    ``IsoMode`` writes one second of modulated heater drive into the AO
    buffer and lets the DAQ replay it indefinitely. The replay re-emits
    sample 0 right after the last sample, so unless the buffer covers an
    integer number of AC cycles there is a phase discontinuity at every
    wrap. Symptom: the AO command itself contains spurious sidebands and
    the recovered C_p is biased.

    Fields
    ------
    cycles
        Number of AC cycles in the buffer (``len * f / fs``).
    cycles_drift
        ``cycles - round(cycles)``, in cycles. Zero means a seamless wrap.
    phase_jump_rad
        ``2 * pi * cycles_drift``. The phase step injected at every wrap.
    leakage_fraction
        Fraction of total AC power *not* at the nearest-bin to ``f``.
        Independent measurement of the same defect via the FFT.
    aliased
        ``True`` if ``frequency >= sample_rate / 2``: the AO command itself
        is below Nyquist (always; AO and AI use the same rate), so this is
        a hard error rather than a leakage warning.
    seamless
        ``True`` iff ``|phase_jump_rad| < tolerance_rad`` and not aliased.
    """

    cycles: float
    cycles_drift: float
    phase_jump_rad: float
    leakage_fraction: float
    aliased: bool
    seamless: bool


def check_ao_period_integrity(
    profile: np.ndarray,
    sample_rate: float,
    frequency: float,
    *,
    tolerance_rad: float = 1e-3,
) -> AOPeriodReport:
    """Report whether an AO modulation buffer wraps cleanly under CONTINUOUS replay.

    Parameters
    ----------
    profile
        AO samples that will be replayed CONTINUOUS. Typically the heater
        drive built by :func:`apply_modulation`.
    sample_rate
        AO sample rate in Hz.
    frequency
        Modulation frequency in Hz.
    tolerance_rad
        Maximum acceptable phase jump at the wrap (default ``1e-3 rad``,
        ``~0.06 deg`` -- about a quarter of a 16-bit DAC LSB at 10 V drive,
        i.e. below DAC resolution).

    Returns
    -------
    AOPeriodReport
    """
    profile = np.asarray(profile, dtype=float)
    if profile.ndim != 1:
        raise ValueError("profile must be 1-D")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if frequency <= 0:
        raise ValueError("frequency must be positive")
    if profile.size == 0:
        raise ValueError("profile must contain at least one sample")

    n = profile.size
    cycles = n * frequency / sample_rate
    nearest = round(cycles)
    cycles_drift = float(cycles - nearest)
    phase_jump_rad = float(2.0 * np.pi * cycles_drift)
    aliased = bool(frequency >= sample_rate / 2.0)

    # Leakage via FFT of the AC component. We subtract the mean (the DC
    # offset has nothing to do with the wrap behaviour) and look at the
    # fraction of power not in the bin closest to ``f``. Done on the full
    # ``n`` (not an integer-cycle slice) on purpose: the question is
    # exactly "how clean is the f-tone in *this* buffer".
    ac = profile - profile.mean()
    spectrum_pwr = np.abs(np.fft.rfft(ac)) ** 2
    total_power = float(spectrum_pwr.sum())
    if total_power > 0 and 0 <= nearest < spectrum_pwr.size:
        leakage_fraction = float(1.0 - spectrum_pwr[nearest] / total_power)
        leakage_fraction = float(min(max(leakage_fraction, 0.0), 1.0))
    else:
        leakage_fraction = float("nan")

    seamless = (abs(phase_jump_rad) < tolerance_rad) and (not aliased)
    return AOPeriodReport(
        cycles=float(cycles),
        cycles_drift=cycles_drift,
        phase_jump_rad=phase_jump_rad,
        leakage_fraction=leakage_fraction,
        aliased=aliased,
        seamless=seamless,
    )


__all__ = [
    "ModulationParams",
    "apply_modulation",
    "lockin_demodulate",
    "fft_demodulate",
    "check_ao_period_integrity",
    "FFTDemodResult",
    "HarmonicAmplitude",
    "AOPeriodReport",
]
