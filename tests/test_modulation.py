"""Tests for the AC modulation generator and lock-in detector."""

from __future__ import annotations

import numpy as np
import pytest

from pioner.shared.modulation import (
    ModulationParams,
    apply_modulation,
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
