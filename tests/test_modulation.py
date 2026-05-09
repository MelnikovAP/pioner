"""Tests for the AC modulation generator and lock-in detector."""

from __future__ import annotations

import numpy as np
import pytest

from pioner.shared.modulation import (
    ModulationParams,
    apply_modulation,
    check_ao_period_integrity,
    fft_demodulate,
    lockin_demodulate,
)


def test_apply_modulation_no_op_when_disabled():
    params = ModulationParams(frequency=37.5, amplitude=0.0, offset=0.0)
    base = np.linspace(0.0, 1.0, 1000)
    out = apply_modulation(np.linspace(0, 1, 1000), base, params)
    np.testing.assert_allclose(out, base)


def test_apply_modulation_adds_sin_and_offset():
    params = ModulationParams(frequency=10.0, amplitude=0.2, offset=0.1)
    t = np.linspace(0.0, 1.0, 1001)
    base = np.full_like(t, 0.5)
    out = apply_modulation(t, base, params)
    expected = 0.5 + 0.1 + 0.2 * np.sin(2 * np.pi * 10 * t)
    np.testing.assert_allclose(out, expected, atol=1e-9)


def test_lockin_recovers_amplitude_and_phase():
    sample_rate = 10_000.0
    duration = 1.0
    t = np.arange(int(sample_rate * duration)) / sample_rate
    expected_amp = 0.4
    expected_phase = 0.6  # signal lags by 0.6 rad
    signal = expected_amp * np.sin(2 * np.pi * 50.0 * t - expected_phase)
    # add a DC offset and a slow drift; the lock-in must reject both
    signal += 0.1 + 0.05 * np.sin(2 * np.pi * 1.0 * t)
    amp, phase = lockin_demodulate(signal, sample_rate=sample_rate, frequency=50.0)
    # Skip a generous IIR settling region (~10 modulation periods on each side)
    # since Butterworth filtfilt has a transient response near the edges.
    settled = slice(2000, -2000)
    np.testing.assert_allclose(amp[settled], expected_amp, atol=0.005)
    np.testing.assert_allclose(phase[settled], expected_phase, atol=0.005)


def test_lockin_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        lockin_demodulate(np.zeros(100), sample_rate=0.0, frequency=10.0)
    with pytest.raises(ValueError):
        lockin_demodulate(np.zeros(100), sample_rate=1000.0, frequency=600.0,
                          bandwidth=600.0)


# ---------------------------------------------------------------------------
# FFT-based demodulation
# ---------------------------------------------------------------------------
def test_fft_demodulate_recovers_fundamental_amp_and_phase():
    """Clean tone -> exact (A, phi) up to numerical roundoff."""
    fs, f = 10_000.0, 50.0
    t = np.arange(int(fs)) / fs   # 1 second, exactly 50 cycles
    A, phi = 0.4, 0.6
    signal = A * np.sin(2 * np.pi * f * t - phi) + 0.7  # DC offset must be rejected
    res = fft_demodulate(signal, fs, f, harmonics=(1,))
    fund = res.fundamental
    assert fund.harmonic == 1
    np.testing.assert_allclose(fund.amplitude, A, atol=1e-10)
    np.testing.assert_allclose(fund.phase, phi, atol=1e-10)


def test_fft_demodulate_extracts_harmonics():
    """2f and 3f are recovered independently of the fundamental."""
    fs, f = 20_000.0, 50.0
    t = np.arange(int(fs)) / fs
    A1, phi1 = 0.4, 0.6
    A2, phi2 = 0.05, -0.2
    A3, phi3 = 0.02, 1.1
    signal = (
        A1 * np.sin(2 * np.pi * f * t - phi1)
        + A2 * np.sin(2 * np.pi * 2 * f * t - phi2)
        + A3 * np.sin(2 * np.pi * 3 * f * t - phi3)
    )
    res = fft_demodulate(signal, fs, f, harmonics=(1, 2, 3))
    h1, h2, h3 = res.harmonics
    np.testing.assert_allclose(h1.amplitude, A1, atol=1e-10)
    np.testing.assert_allclose(h1.phase, phi1, atol=1e-10)
    np.testing.assert_allclose(h2.amplitude, A2, atol=1e-10)
    np.testing.assert_allclose(h2.phase, phi2, atol=1e-10)
    np.testing.assert_allclose(h3.amplitude, A3, atol=1e-10)
    np.testing.assert_allclose(h3.phase, phi3, atol=1e-10)
    # Clean signal -> negligible leakage (only the integer-cycle window
    # endpoint roundoff).
    assert res.leakage_fraction < 1e-12


def test_fft_demodulate_phase_matches_lockin():
    """FFT and time-domain lock-in must agree on a stationary signal.

    Otherwise downstream code that compares them (the IsoMode flow) would
    raise false alarms about the AO period or thermal transients.
    """
    fs, f = 20_000.0, 37.5
    t = np.arange(int(fs)) / fs   # 1 s, fits an integer-cycle FFT window
    A, phi = 0.3, 0.42
    signal = A * np.sin(2 * np.pi * f * t - phi) + 0.5
    res = fft_demodulate(signal, fs, f, harmonics=(1,))
    amp_lock, phase_lock = lockin_demodulate(signal, fs, f)
    # Settled region only (filtfilt transient ~10 periods on each edge).
    settled = slice(int(fs * 0.3), int(fs * 0.7))
    np.testing.assert_allclose(res.fundamental.amplitude, A, atol=1e-9)
    np.testing.assert_allclose(np.mean(amp_lock[settled]), A, atol=5e-3)
    # Phases agree to milliradian -- the integer-cycle FFT is bias-free,
    # the lock-in has filter-shape ripple.
    np.testing.assert_allclose(res.fundamental.phase, phi, atol=1e-9)
    np.testing.assert_allclose(np.mean(phase_lock[settled]), phi, atol=5e-3)


def test_fft_demodulate_leakage_flags_off_grid_tone():
    """A tone NOT at an integer-cycle bin shows up as leakage."""
    fs, f = 10_000.0, 50.0
    t = np.arange(int(fs)) / fs
    # Fundamental at 50 Hz + interferer at 73 Hz (not a multiple of f).
    signal = (
        0.4 * np.sin(2 * np.pi * f * t)
        + 0.4 * np.sin(2 * np.pi * 73.0 * t)
    )
    res = fft_demodulate(signal, fs, f, harmonics=(1, 2, 3))
    # Half the AC power is at 73 Hz -> leakage near 0.5.
    assert 0.4 < res.leakage_fraction < 0.6


def test_fft_demodulate_handles_aliased_harmonic():
    """A harmonic above Nyquist returns NaN, not an error."""
    fs, f = 200.0, 50.0
    t = np.arange(int(fs)) / fs
    signal = 0.4 * np.sin(2 * np.pi * f * t)
    res = fft_demodulate(signal, fs, f, harmonics=(1, 2, 3))
    h1, h2, h3 = res.harmonics
    assert h1.amplitude == pytest.approx(0.4, abs=1e-10)
    # h=2 -> 100 Hz = Nyquist, falls on the rfft last bin (real-only); h=3
    # is above Nyquist and must alias / be reported as NaN.
    assert np.isnan(h3.amplitude)
    assert np.isnan(h3.phase)


def test_fft_demodulate_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        fft_demodulate(np.zeros(100), sample_rate=0.0, frequency=10.0)
    with pytest.raises(ValueError):
        fft_demodulate(np.zeros(100), sample_rate=1000.0, frequency=600.0)
    with pytest.raises(ValueError):
        fft_demodulate(np.zeros(5), sample_rate=1000.0, frequency=10.0)
    with pytest.raises(ValueError):
        fft_demodulate(np.zeros(100), sample_rate=1000.0, frequency=10.0,
                       harmonics=(0,))


# ---------------------------------------------------------------------------
# AO modulation buffer integrity
# ---------------------------------------------------------------------------
def test_ao_period_integrity_seamless_when_integer_cycles():
    """An integer-cycle buffer must report seamless = True with zero drift."""
    fs, f = 20_000.0, 40.0       # 40 cycles per second exactly
    n = 20_000                    # 1 s buffer
    t = np.arange(n) / fs
    profile = 0.3 + 0.1 * np.sin(2 * np.pi * f * t)
    report = check_ao_period_integrity(profile, fs, f)
    assert report.seamless
    assert abs(report.cycles_drift) < 1e-9
    assert abs(report.phase_jump_rad) < 1e-9
    assert report.leakage_fraction < 1e-9
    assert not report.aliased


def test_ao_period_integrity_flags_production_iso_settings():
    """Default iso settings (37.5 Hz at 20 kHz, 1 s buffer) are NOT seamless.

    This is a real defect in the current production configuration: 37.5
    cycles in the buffer means a pi-rad phase jump at every wrap. The check
    must catch it so the operator gets a warning.
    """
    fs, f = 20_000.0, 37.5
    n = 20_000
    t = np.arange(n) / fs
    profile = 0.3 + 0.1 * np.sin(2 * np.pi * f * t)
    report = check_ao_period_integrity(profile, fs, f)
    assert not report.seamless
    np.testing.assert_allclose(report.cycles, 37.5)
    np.testing.assert_allclose(abs(report.cycles_drift), 0.5)
    np.testing.assert_allclose(abs(report.phase_jump_rad), np.pi, atol=1e-12)
    # With cycles=37.5 the AC power is split between bins 37 and 38, so
    # the nearest-bin captures only ~half. Leakage ~0.4..0.6.
    assert 0.3 < report.leakage_fraction < 0.7


def test_ao_period_integrity_19200_sample_buffer_is_clean():
    """Sizing the buffer to an integer-cycle multiple at 37.5 Hz fixes it."""
    fs, f = 20_000.0, 37.5
    n = 19_200    # 36 cycles -> integer
    t = np.arange(n) / fs
    profile = 0.3 + 0.1 * np.sin(2 * np.pi * f * t)
    report = check_ao_period_integrity(profile, fs, f)
    assert report.seamless
    assert report.leakage_fraction < 1e-9


def test_ao_period_integrity_flags_aliased_frequency():
    """f >= sample_rate / 2 must be reported as aliased and not seamless."""
    fs, f = 100.0, 60.0   # well above Nyquist=50
    profile = np.zeros(100)
    report = check_ao_period_integrity(profile, fs, f)
    assert report.aliased
    assert not report.seamless


def test_ao_period_integrity_rejects_bad_inputs():
    with pytest.raises(ValueError):
        check_ao_period_integrity(np.array([]), 1000.0, 10.0)
    with pytest.raises(ValueError):
        check_ao_period_integrity(np.zeros(100), 0.0, 10.0)
    with pytest.raises(ValueError):
        check_ao_period_integrity(np.zeros(100), 1000.0, 0.0)
