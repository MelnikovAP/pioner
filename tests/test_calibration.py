"""Tests for ``pioner.shared.calibration`` and ``pioner.shared.utils``."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest

from pioner.shared.calibration import Calibration
from pioner.shared.constants import DEFAULT_CALIBRATION_FILE_REL_PATH
from pioner.shared.utils import temperature_to_voltage, voltage_to_temperature


def test_reads_default_calibration_from_package_rel_path():
    """Bundled defaults must resolve through ``DEFAULT_CALIBRATION_FILE_REL_PATH`` (Tango / server)."""
    assert os.path.isfile(DEFAULT_CALIBRATION_FILE_REL_PATH), (
        f"missing bundled default calibration: {DEFAULT_CALIBRATION_FILE_REL_PATH!r}"
    )
    cal = Calibration()
    cal.read(DEFAULT_CALIBRATION_FILE_REL_PATH)
    assert cal.safe_voltage > 0.0


def test_default_calibration_is_identity():
    cal = Calibration()
    # Stay within the default safe_voltage (8 V): voltage_to_temperature clamps
    # its input to [0, safe_voltage], so a point above it would not round-trip.
    voltages = np.array([0.0, 1.0, 5.0, 8.0])
    temps = voltage_to_temperature(voltages, cal)
    np.testing.assert_allclose(temps, voltages)


def test_temperature_to_voltage_logs_when_clamping(caplog):
    """The defense-in-depth clamp is no longer silent: an out-of-range
    temperature is capped to the safe envelope AND logged (P1-4)."""
    cal = Calibration()  # identity: max_temp == safe_voltage
    with caplog.at_level(logging.WARNING, logger="pioner.shared.utils"):
        out = temperature_to_voltage(np.array([5.0, cal.max_temp + 50.0]), cal)
    assert out[-1] == pytest.approx(cal.safe_voltage, abs=1e-3)  # capped
    assert any("clamped" in r.message for r in caplog.records)


def test_temperature_to_voltage_clamps_to_safe_voltage():
    cal = Calibration()
    too_hot = np.array([cal.max_temp + 100.0])
    voltage = temperature_to_voltage(too_hot, cal)
    assert voltage[0] <= cal.safe_voltage


def test_temperature_to_voltage_handles_array_input():
    cal = Calibration()
    target = np.linspace(0.0, cal.max_temp - 0.1, 1000)
    voltage = temperature_to_voltage(target, cal)
    # Round-trip should land within one grid step (~1 mV).
    recovered = voltage_to_temperature(voltage, cal)
    np.testing.assert_allclose(recovered, target, atol=0.02)


def test_calibration_round_trip(tmp_path: Path):
    cal = Calibration()
    cal.comment = "test"
    cal.theater0 = -2.4
    cal.theater1 = 8.0
    cal.theater2 = -0.43
    cal.hardware.gain_utpl = 13.0
    out = tmp_path / "calib.json"
    cal.write(str(out))
    other = Calibration()
    other.read(str(out))
    assert other.comment == "test"
    assert other.hardware.gain_utpl == 13.0
    assert other.theater0 == pytest.approx(-2.4)


def test_calibration_rejects_wrong_extension(tmp_path: Path):
    bogus = tmp_path / "calib.txt"
    bogus.write_text(json.dumps({"Calibration coeff": {}}))
    cal = Calibration()
    with pytest.raises(ValueError):
        cal.read(str(bogus))


def test_calibration_rejects_missing_block(tmp_path: Path):
    bogus = tmp_path / "calib.json"
    bogus.write_text(json.dumps({"Info": "x"}))
    cal = Calibration()
    with pytest.raises(ValueError):
        cal.read(str(bogus))


def test_temperature_to_voltage_empty_input():
    cal = Calibration()
    out = temperature_to_voltage([], cal)
    assert out.size == 0


def test_temperature_to_voltage_non_monotonic_raises():
    """Catastrophic non-monotonicity (overall trend going *down*) must raise."""
    cal = Calibration()
    cal.theater0 = -1.0
    cal.theater1 = 0.0
    cal.theater2 = 0.0
    cal._add_params()
    with pytest.raises(ValueError, match="not monotonic"):
        temperature_to_voltage(np.array([0.5]), cal)


def test_production_calibration_polynomial_inverts():
    """Real chip calibration is *almost* monotonic with a small sub-zero dip
    near V=0; this must still produce sensible voltages.
    """
    cal = Calibration()
    cal.theater0 = -2.425
    cal.theater1 = 8.0393
    cal.theater2 = -0.42986
    cal._add_params()

    # Mid-range temperatures recover their original voltage within 1 grid step.
    voltages = np.array([1.0, 2.0, 4.0, 7.0])
    temps = voltage_to_temperature(voltages, cal)
    recovered = temperature_to_voltage(temps, cal)
    np.testing.assert_allclose(recovered, voltages, atol=2e-3)

    # Asking for T < T(V=0) clamps to V=0.
    sub_zero = temperature_to_voltage(np.array([-1.0]), cal)
    assert sub_zero[0] == 0.0


def test_default_calibration_pins_identity_constants():
    """Pin the bundled default calibration to its identity coefficients.

    Until an SI recalibration procedure exists (todo P2-21), the production
    pipeline relies on these being the dimensionless identity values: the
    heater-current proxy ``ih = ihtr0 + ihtr1 * V_ch0`` must stay ``V_ch0``
    (ihtr0=0, ihtr1=1), and the voltage/temperature polynomials must stay
    identity. If any of these drift the live readouts silently change scale,
    so this test fails loudly to force a deliberate recalibration commit.
    """
    cal = Calibration()
    cal.read(DEFAULT_CALIBRATION_FILE_REL_PATH)

    # Heater current proxy: identity (see modes.apply_calibration + P2-21).
    assert cal.ihtr0 == 0.0
    assert cal.ihtr1 == 1.0
    # Heater voltage offset/gain inside the Rhtr formula: identity.
    assert cal.uhtr0 == 0.0
    assert cal.uhtr1 == 1.0
    # Thtr / Thtrd polynomials: identity (proxy Rhtr passes through unscaled).
    assert (cal.thtr0, cal.thtr1, cal.thtr2, cal.thtrcorr) == (0.0, 1.0, 0.0, 0.0)
    assert (cal.thtrd0, cal.thtrd1, cal.thtrd2, cal.thtrdcorr) == (0.0, 1.0, 0.0, 0.0)
    # Theater (T = f(U)) and the lock-in amplitude correction: identity.
    assert (cal.theater0, cal.theater1, cal.theater2) == (0.0, 1.0, 0.0)
    assert (cal.ac0, cal.ac1, cal.ac2, cal.ac3) == (0.0, 1.0, 0.0, 0.0)
    # The amplitude-correction divider must be OFF in the bundled default: the
    # placeholder ac* give kamp(T)=T (not 1), so applying it would divide the
    # amplitude by the temperature. P1-32 keeps it opt-in.
    assert cal.amplitude_correction_enabled is False


def test_kamp_polynomial_scalar_and_array():
    """kamp(T) = ac0 + ac1*T + ac2*T^2 + ac3*T^3 for scalars and arrays."""
    cal = Calibration()
    cal.ac0, cal.ac1, cal.ac2, cal.ac3 = 0.961, 0.00131, 3.12e-07, 0.0
    # Scalar.
    assert cal.kamp(0.0) == pytest.approx(0.961)
    assert cal.kamp(100.0) == pytest.approx(0.961 + 0.00131 * 100 + 3.12e-07 * 1e4)
    # Array preserves shape.
    out = cal.kamp(np.array([0.0, 100.0]))
    np.testing.assert_allclose(out, [0.961, 0.961 + 0.131 + 3.12e-07 * 1e4])


def test_amplitude_correction_enabled_round_trips(tmp_path: Path):
    """The opt-in flag persists through write/read; absent -> defaults off."""
    cal = Calibration()
    assert cal.amplitude_correction_enabled is False  # default-constructed
    cal.amplitude_correction_enabled = True
    out = tmp_path / "calib.json"
    cal.write(str(out))
    other = Calibration()
    other.read(str(out))
    assert other.amplitude_correction_enabled is True

    # A legacy file with no "enabled" key reads back as off.
    data = json.loads(out.read_text())
    del data["Calibration coeff"]["Amplitude correction"]["enabled"]
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(data))
    legacy_cal = Calibration()
    legacy_cal.read(str(legacy))
    assert legacy_cal.amplitude_correction_enabled is False


# --- P1-33: in-situ R-correction auto-zero -----------------------------------

def test_solve_rhcorr_converges_identity_polynomial():
    """Identity Thtr poly: T(corr) = R + corr; trimming to t_target gives a
    correction of exactly (t_target - R)."""
    r, target = 100.0, 105.0
    rep = Calibration.solve_rhcorr(0.0, 1.0, 0.0, r, target)
    assert rep["converged"] is True
    assert rep["diverged"] is False
    assert rep["corr"] == pytest.approx(5.0, abs=0.01)
    assert abs(rep["residual_c"]) < 0.01


def test_solve_rhcorr_converges_production_polynomial():
    """A realistic quadratic Thtr poly converges so Thtr(corr) hits the target."""
    c0, c1, c2 = -1069.7, 0.78336, -8.67e-5
    r, target = 1450.0, 40.0
    rep = Calibration.solve_rhcorr(c0, c1, c2, r, target)
    assert rep["converged"] is True
    thtr = c0 + c1 * (r + rep["corr"]) + c2 * (r + rep["corr"]) ** 2
    assert thtr == pytest.approx(target, abs=0.01)


def test_solve_rhcorr_refines_from_corr_start():
    """The iteration refines an existing correction rather than resetting it."""
    rep = Calibration.solve_rhcorr(0.0, 1.0, 0.0, 100.0, 105.0, corr_start=4.0)
    assert rep["corr"] == pytest.approx(5.0, abs=0.01)


def test_solve_rhcorr_diverges_resets_to_zero():
    """A polynomial whose fixed-point diverges resets corr to 0 (Bondar guard)."""
    rep = Calibration.solve_rhcorr(0.0, -50.0, 0.0, 1.0, 1000.0)
    assert rep["diverged"] is True
    assert rep["converged"] is False
    assert rep["corr"] == 0.0


def test_solve_rhcorr_rejects_zero_or_nonfinite_resistance():
    """No correction is attempted when the heater current (R) is undefined."""
    rep = Calibration.solve_rhcorr(0.0, 1.0, 0.0, 0.0, 105.0, corr_start=3.0)
    assert rep["converged"] is False
    assert rep["corr"] == 3.0  # left at corr_start
    rep_nan = Calibration.solve_rhcorr(0.0, 1.0, 0.0, float("nan"), 105.0)
    assert rep_nan["converged"] is False


def test_compute_rhcorr_mutates_the_right_field():
    """compute_rhcorr stores into thtrcorr (heater) or thtrdcorr (differential)."""
    cal = Calibration()  # identity Thtr / Thtrd polynomials
    rep = cal.compute_rhcorr(100.0, 105.0)
    assert rep["field"] == "thtrcorr"
    assert rep["corr_old"] == 0.0
    assert cal.thtrcorr == pytest.approx(5.0, abs=0.01)
    assert cal.thtrdcorr == 0.0  # untouched

    rep_d = cal.compute_rhcorr(100.0, 92.0, differential=True)
    assert rep_d["field"] == "thtrdcorr"
    assert cal.thtrdcorr == pytest.approx(-8.0, abs=0.01)
    assert cal.thtrcorr == pytest.approx(5.0, abs=0.01)  # heater still as before


# --- P2-24: broken/shorted heater classification ---------------------------

def test_classify_heater_resistance():
    cal = Calibration()  # defaults: broken > 9000, shorted < 50 (proxy V/V)
    assert cal.classify_heater_resistance(1700.0) == "ok"
    assert cal.classify_heater_resistance(20000.0) == "broken"
    assert cal.classify_heater_resistance(10.0) == "shorted"
    assert cal.classify_heater_resistance(float("nan")) == "unknown"  # idle


def test_heater_threshold_round_trips(tmp_path: Path):
    cal = Calibration()
    cal.r_heater_broken, cal.r_heater_shorted = 12345.0, 7.0
    out = tmp_path / "c.json"
    cal.write(str(out))
    other = Calibration()
    other.read(str(out))
    assert other.r_heater_broken == 12345.0 and other.r_heater_shorted == 7.0
    # Legacy file without the keys -> defaults.
    data = json.loads(out.read_text())
    del data["Calibration coeff"]["R heater broken"]
    del data["Calibration coeff"]["R heater shorted"]
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(data))
    lc = Calibration()
    lc.read(str(legacy))
    assert lc.r_heater_broken == 9000.0 and lc.r_heater_shorted == 50.0


def test_read_malformed_calibration_raises_clear_error(tmp_path: Path):
    """A calibration file missing a required field raises a clear ValueError
    naming the file, not a bare KeyError (P1-16)."""
    data = {"Calibration coeff": {"Utpl": {"0": 0.0}}}  # almost everything missing
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(data))
    cal = Calibration()
    with pytest.raises(ValueError, match="malformed"):
        cal.read(str(p))
