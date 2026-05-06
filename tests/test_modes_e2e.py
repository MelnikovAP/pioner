"""End-to-end smoke tests for the three calorimetry modes on the mock DAQ."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pioner.back.modes import (
    DEFAULT_AI_CHANNELS,
    FastHeat,
    IsoMode,
    SlowMode,
    create_mode,
)


@pytest.fixture
def fast_programs():
    return {
        "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 250, 750, 1000], "volt": [0, 1, 1, 0]},
        "ch2": {"time": [0, 1000], "volt": [5, 5]},
    }


def test_fast_mode_no_point_loss(connected_daq, settings, calibration, fast_programs):
    settings.modulation = settings.modulation.with_amplitude(0.0)  # disable AC
    mode = FastHeat(connected_daq, settings, calibration, fast_programs)
    mode.arm()
    df = mode.run()

    expected_samples = settings.ai_params.sample_rate * 1  # 1 second
    assert len(df) == expected_samples, "fast mode lost samples"
    for col in ("time", "Taux", "Thtr", "temp", "temp-hr", "Uref"):
        assert col in df.columns, f"missing column {col}"


def test_slow_mode_produces_lockin_columns(
    connected_daq, settings, calibration, fast_programs
):
    # Re-use the same shape but for 2 seconds.
    programs = {
        "ch0": {"time": [0, 2000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 2000], "volt": [0, 1]},
    }
    # Turn modulation on at 100 Hz / 0.1 V to keep the test deterministic.
    settings.modulation = settings.modulation.with_amplitude(0.1)
    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    df = mode.run()
    expected_samples = settings.ai_params.sample_rate * 2
    assert len(df) == expected_samples
    assert "temp-hr_amp" in df.columns
    assert "temp-hr_phase" in df.columns


def test_iso_mode_streams_into_dataframe(
    connected_daq, settings, calibration
):
    programs = {"ch1": {"volt": 0.5}}
    iso = IsoMode(
        connected_daq, settings, calibration, programs,
        ring_buffer_seconds=2.0,
    )
    iso.arm()
    df = iso.run(duration_seconds=1.0)
    # The ring buffer should hold roughly 1 s of samples; allow a wide
    # tolerance because the 0.5 s flip granularity rounds down.
    assert 0.4 * settings.ai_params.sample_rate <= len(df) <= 1.2 * settings.ai_params.sample_rate


def test_create_mode_factory(connected_daq, settings, calibration, fast_programs):
    mode = create_mode("fast", connected_daq, settings, calibration, fast_programs)
    assert isinstance(mode, FastHeat)


def test_create_mode_unknown_raises(
    connected_daq, settings, calibration, fast_programs
):
    with pytest.raises(KeyError):
        create_mode("totally_made_up", connected_daq, settings, calibration, fast_programs)


def test_validate_rejects_non_second_durations(
    connected_daq, settings, calibration
):
    bad = {"ch1": {"time": [0, 1500], "volt": [0, 1]}}
    mode = FastHeat(connected_daq, settings, calibration, bad)
    with pytest.raises(ValueError, match="whole number of seconds"):
        mode.arm()


def test_validate_rejects_inconsistent_durations(
    connected_daq, settings, calibration
):
    bad = {
        "ch0": {"time": [0, 1000], "volt": [0, 0]},
        "ch1": {"time": [0, 2000], "volt": [0, 1]},
    }
    mode = FastHeat(connected_daq, settings, calibration, bad)
    with pytest.raises(ValueError, match="inconsistent"):
        mode.arm()


def test_fast_mode_with_temperature_program_runs_calibration_path(
    connected_daq, settings, calibration
):
    """A program in °C must go through ``temperature_to_voltage`` correctly."""
    settings.modulation = settings.modulation.with_amplitude(0.0)
    # Use a non-trivial production-like polynomial on a copy of the calibration
    # so the round-trip exercises the inversion logic.
    calibration.theater0 = -2.425
    calibration.theater1 = 8.0393
    calibration.theater2 = -0.42986
    calibration._add_params()

    programs = {
        "ch1": {"time": [0, 500, 1000], "temp": [10, 100, 10]},
    }
    mode = FastHeat(connected_daq, settings, calibration, programs)
    mode.arm()
    profile = mode.voltage_profiles["ch1"]
    # Start and end of program correspond to T=10 °C.
    # Voltage that produces T=10 must be between 0 and ~3 V.
    assert 0.0 <= profile[0] <= 5.0
    assert 0.0 <= profile[-1] <= 5.0
    # Mid point T=100 °C: voltage should be higher than for T=10 °C.
    assert profile[len(profile) // 2] > profile[0]
    df = mode.run()
    assert len(df) == settings.ai_params.sample_rate
