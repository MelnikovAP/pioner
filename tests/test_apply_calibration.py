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

# pyright: reportGeneralTypeIssues=false
# pandas-stubs returns ``Series | DataFrame | bool`` from ``df["col"].isna().any()``;
# pyright then refuses to use the result in boolean context. Runtime-verified.
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


def test_rhtr_units_are_ohms_with_si_calibration():
    """Under a *hypothetical* SI calibration (``ihtr1 = 1/R_shunt``) and a known
    V/I pair, ``Thtr`` must come out in a physically plausible range (tens to
    hundreds of C).

    NOTE: production (and the bundled defaults) use the identity ``ihtr0=0,
    ihtr1=1`` -- ``ih = U_AI0`` is a voltage proxy, ``Rhtr`` dimensionless (see
    P0-3). This test deliberately sets the future SI calibration (P2-21) to
    guard the arithmetic, NOT the production identity.

    Regression: the historical formula multiplied both V_AO and V_shunt by
    1000 before subtracting and dividing by I (in A), producing R in
    milliohms instead of ohms. With the production ``Thtr`` polynomial this
    drove ``thtr2 * R^2`` to ~ -1e8 C and was completely unusable.
    """
    cal = Calibration()
    R_shunt = 1700.0
    cal.ihtr0 = 0.0
    cal.ihtr1 = 1.0 / R_shunt          # hypothetical SI calibration (P2-21), not production
    cal.uhtr0 = 0.0
    cal.uhtr1 = 1.0
    cal.thtr0 = -1069.7                 # production polynomial
    cal.thtr1 = 0.78336
    cal.thtr2 = -8.67e-5
    cal.thtrcorr = 0.0

    # Heater at ~ room temperature (R = 1700 Ohm), I = 1 mA:
    #   V_shunt = R_shunt * I = 1.7 V
    #   V_AO    = (R_heater + R_shunt) * I = 3.4 V (AI ch5 sees the drive)
    raw = _make_raw_frame(100)
    raw[0] = 1.7
    raw[5] = 3.4

    out = apply_calibration(raw, sample_rate=20000.0, calibration=cal, voltage_profiles={})
    thtr = out["Thtr"].to_numpy()

    # Polynomial at R = 1700 Ohm gives ~ 11.5 C; allow generous tolerance
    # because the formula's "R - R_shunt" interpretation depends on the
    # circuit topology, but anything in [-50, +200] C is the correct order
    # of magnitude. The pre-fix code produced numbers around -10^8 C.
    assert np.all(np.isfinite(thtr))
    assert -50.0 <= thtr.mean() <= 200.0, (
        f"Thtr out of physical range: mean={thtr.mean()} (expected ~10 C)"
    )


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


def test_apply_calibration_scales_channels_once_and_leaves_input_untouched():
    """P1-3 regression: temp / temp-hr come from the raw AI channels scaled
    exactly once (no in-place double-mutation), and the caller's frame is not
    modified. A future reorder that fed an already-scaled column back in would
    flip the expected values here.
    """
    cal = Calibration()
    sr = 20000
    raw = _make_raw_frame(sr)          # 1 s, all channels zero
    raw[1] = 0.02                      # UMOD_AI (ch1) -> temp-hr
    raw[4] = 0.03                      # UTPL_AI (ch4) -> temp
    raw_before = raw.copy(deep=True)

    out = apply_calibration(
        raw, sample_rate=sr, calibration=cal, voltage_profiles={},
        ai_channels=list(range(6)),
    )

    # Caller's frame must be untouched.
    pd.testing.assert_frame_equal(raw, raw_before)

    hw = cal.hardware
    ax_hr = 0.02 * (1000.0 / hw.gain_umod) + cal.utpl0
    expected_hr = cal.ttpl0 * ax_hr + cal.ttpl1 * ax_hr**2
    np.testing.assert_allclose(out["temp-hr"].to_numpy(), expected_hr)

    ax = 0.03 * (1000.0 / hw.gain_utpl) + cal.utpl0
    expected_temp = cal.ttpl0 * ax + cal.ttpl1 * ax**2  # + Taux (0 here)
    np.testing.assert_allclose(out["temp"].to_numpy(), expected_temp)

    # Raw integer-named channel columns must not survive in the output.
    assert not any(isinstance(c, int) for c in out.columns)
