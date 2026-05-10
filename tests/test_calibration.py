"""Tests for ``pioner.shared.calibration`` and ``pioner.shared.utils``."""

from __future__ import annotations

import json
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
    voltages = np.array([0.0, 1.0, 5.0, 9.0])
    temps = voltage_to_temperature(voltages, cal)
    np.testing.assert_allclose(temps, voltages)


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
