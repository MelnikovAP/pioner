"""Unit tests for :func:`pioner.back.modes.apply_calibration`.

These cover post-processing edge cases that are easy to break and hard to
notice in the e2e smoke tests:

* ``Uref`` for a continuous-AO (iso) experiment must be tiled to the AI
  length, not NaN-padded — the buffer physically *does* repeat.
* ``Thtr`` must be NaN where the heater current is below the noise floor;
  emitting a sentinel like ``-1070 °C`` (the value that comes out of the
  production polynomial when ``R = 0``) turns up as a phantom point on the
  calorimetry curve.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pioner.back.modes import apply_calibration
from pioner.shared.calibration import Calibration


def _make_raw_frame(samples: int, n_channels: int = 6) -> pd.DataFrame:
    """Synthesise a raw AI frame with channels 0..n_channels-1 all at zero."""
    return pd.DataFrame({c: np.zeros(samples) for c in range(n_channels)})


def test_uref_is_tiled_for_continuous_iso_buffer():
    """A 1 s AO buffer driving a 3 s AI capture must produce a 3 s Uref column."""
    cal = Calibration()
    sample_rate = 20000
    duration_s = 3
    raw = _make_raw_frame(sample_rate * duration_s)
    # Iso/CONTINUOUS AO: a single second of voltage that the driver replays.
    one_second_profile = np.linspace(0.0, 1.0, sample_rate)
    profiles = {"ch1": one_second_profile}

    out = apply_calibration(raw, sample_rate=sample_rate, calibration=cal, voltage_profiles=profiles)

    assert "Uref" in out.columns
    assert len(out["Uref"]) == sample_rate * duration_s
    assert not out["Uref"].isna().any(), "Uref must not contain NaNs after tiling"
    # Each second-long block must equal the original profile.
    for second in range(duration_s):
        chunk = out["Uref"].to_numpy()[second * sample_rate : (second + 1) * sample_rate]
        np.testing.assert_allclose(chunk, one_second_profile)


def test_uref_is_tiled_for_dc_iso_single_sample_profile():
    """DC iso uses a single-sample AO profile; the column must hold that constant."""
    cal = Calibration()
    sample_rate = 20000
    raw = _make_raw_frame(sample_rate * 2)
    profiles = {"ch1": np.array([0.7])}

    out = apply_calibration(raw, sample_rate=sample_rate, calibration=cal, voltage_profiles=profiles)

    assert len(out["Uref"]) == sample_rate * 2
    assert not out["Uref"].isna().any()
    np.testing.assert_allclose(out["Uref"].to_numpy(), 0.7)


def test_thtr_is_nan_when_heater_current_is_zero():
    """A frame with zero current in channel 0 must yield NaN Thtr, not a sentinel."""
    cal = Calibration()
    # Production-like Thtr polynomial that turns ``R=0`` into ~ -1070 °C.
    cal.thtr0 = -1069.7
    cal.thtr1 = 0.78336
    cal.thtr2 = -8.67e-5
    cal.thtrcorr = 0.0

    raw = _make_raw_frame(1000)
    out = apply_calibration(raw, sample_rate=20000.0, calibration=cal, voltage_profiles={})

    assert "Thtr" in out.columns
    assert out["Thtr"].isna().all(), (
        f"Expected all-NaN Thtr when heater current is 0; got {out['Thtr'].describe()}"
    )


def test_thtr_is_finite_when_heater_current_is_present():
    """Sanity: with non-zero current the polynomial fires and Thtr is a real number."""
    cal = Calibration()
    raw = _make_raw_frame(500)
    raw[0] = 0.005  # nonzero current
    raw[5] = 0.001  # nonzero heater voltage

    out = apply_calibration(raw, sample_rate=20000.0, calibration=cal, voltage_profiles={})

    assert "Thtr" in out.columns
    assert np.isfinite(out["Thtr"]).all()


def test_apply_calibration_preserves_length_and_drops_raw_columns():
    cal = Calibration()
    raw = _make_raw_frame(2000)
    out = apply_calibration(raw, sample_rate=20000.0, calibration=cal, voltage_profiles={})
    assert len(out) == 2000
    # All raw integer-named columns must be gone in the public output.
    for raw_col in (0, 1, 3, 4, 5):
        assert raw_col not in out.columns
    # Time axis must always be present.
    assert "time" in out.columns


def test_apply_calibration_handles_empty_input():
    cal = Calibration()
    out = apply_calibration(pd.DataFrame(), sample_rate=20000.0, calibration=cal, voltage_profiles={})
    assert out.empty
