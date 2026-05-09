"""End-to-end smoke tests for the three calorimetry modes on the mock DAQ."""

from __future__ import annotations

import threading
import time

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


def test_iso_mode_with_modulation_emits_fft_attrs_and_warns_on_non_seamless(
    connected_daq, settings, calibration, caplog
):
    """IsoMode + AC modulation: FFT scalars in df.attrs and AO warning logged.

    The default settings (f=37.5 Hz at fs=20 kHz, 1 s buffer) are NOT
    seamless on the AO wrap, so the IsoMode arm step must log a warning
    and ``run()`` must still produce both the per-sample lock-in columns
    and the scalar FFT attrs.
    """
    import logging

    # Pick an integer-cycle f to keep the AC test deterministic but rely
    # on the default fs=20000 Hz which gives 40 cycles -> seamless.
    settings.modulation = settings.modulation.with_amplitude(0.1)
    iso = IsoMode(
        connected_daq, settings, calibration, {"ch1": {"volt": 0.4}},
        ring_buffer_seconds=2.0,
    )
    with caplog.at_level(logging.WARNING, logger="pioner.back.modes"):
        iso.arm()
    # Default f_mod is 37.5 Hz (see settings/settings.json); the default
    # buffer is 1 s; cycles=37.5 -> non-seamless -> warning expected.
    if abs((settings.ai_params.sample_rate * settings.modulation.frequency)
           % settings.ai_params.sample_rate) > 0:
        assert any("not seamless" in rec.message.lower() for rec in caplog.records), (
            "Expected a non-seamless AO warning at default 37.5 Hz / 20 kHz / 1 s"
        )

    # AO integrity report is exposed for callers that want to introspect it.
    assert iso._ao_period_report is not None
    assert iso._ao_period_report.cycles == pytest.approx(37.5)

    df = iso.run(duration_seconds=1.0)
    # Per-sample lock-in columns survive (existing contract).
    assert "temp-hr_amp" in df.columns
    assert "temp-hr_phase" in df.columns
    # Scalar FFT results land on df.attrs.
    assert "temp-hr_fft" in df.attrs
    fft_attrs = df.attrs["temp-hr_fft"]
    assert set(fft_attrs.keys()) >= {1, 2, 3}
    # Mock signal contains a deterministic ~196 Hz tone (mock_uldaq.py:362)
    # plus the modulation echo, so amplitude at 1f is non-NaN and finite.
    assert np.isfinite(fft_attrs[1]["amplitude"])
    assert np.isfinite(fft_attrs[1]["phase"])
    assert "temp-hr_fft_leakage" in df.attrs
    assert 0.0 <= df.attrs["temp-hr_fft_leakage"] <= 1.0
    assert df.attrs["temp-hr_fft_window_samples"] > 0


def test_iso_ac_with_hardware_trigger_runs_clean(
    connected_daq, settings, calibration
):
    """Iso AC must respect ``hardware_trigger`` (regression).

    The iso/slow CONTINUOUS path used to ignore ``hardware_trigger``: only
    ``finite_scan`` honoured it. Without the trigger, AO and AI start
    separately (~100 us apart), which biases the FFT phase recovery for
    higher modulation frequencies. After the fix, ``ao_modulated`` arms AO
    with ``EXTTRIGGER`` and ``start_ring_buffer`` arms AI with the same
    flag, then fires the trigger once both are gated.
    """
    settings.modulation = settings.modulation.with_amplitude(0.1)
    settings.daq_params.hardware_trigger = True
    try:
        iso = IsoMode(
            connected_daq, settings, calibration, {"ch1": {"volt": 0.4}},
            ring_buffer_seconds=2.0,
        )
        iso.arm()
        df = iso.run(duration_seconds=1.0)
    finally:
        settings.daq_params.hardware_trigger = False

    # The mock implements EXTTRIGGER as a synchronised release so a triggered
    # iso run must still produce a non-empty DataFrame; this guards against
    # regressions where AO/AI stay armed forever and the worker yields zero
    # samples.
    assert len(df) > 0
    assert "temp-hr" in df.columns


def test_fast_mode_with_hardware_trigger_runs_clean(
    connected_daq, settings, calibration, fast_programs
):
    """``hardware_trigger`` should produce the same result as the legacy path.

    The mock implements EXTTRIGGER as a synchronised release of the AO and
    AI workers (see ``_SharedScanState.fire_trigger``), so when the flag is
    on we still get a full DataFrame back; this guards against regressions
    that would leave the scans armed but never fired (and thus return zero
    samples).
    """
    settings.modulation = settings.modulation.with_amplitude(0.0)
    settings.daq_params.hardware_trigger = True
    try:
        mode = FastHeat(connected_daq, settings, calibration, fast_programs)
        mode.arm()
        df = mode.run()
    finally:
        settings.daq_params.hardware_trigger = False

    assert len(df) == settings.ai_params.sample_rate
    for col in ("time", "Taux", "Thtr", "temp", "temp-hr", "Uref"):
        assert col in df.columns


def test_ao_set_rejects_out_of_range_voltage(connected_daq, settings, calibration):
    """Direct ``em.ao_set`` calls beyond the configured analog range must fail loud."""
    from pioner.back.experiment_manager import ExperimentManager

    em = ExperimentManager(connected_daq, settings)
    # range_id = 5 in default_settings.json -> +/-10 V.
    with pytest.raises(ValueError, match="exceeds the configured analog range"):
        em.ao_set(1, 50.0)
    # In-range still works.
    em.ao_set(1, 9.5)


def test_iso_dc_temp_program_goes_through_calibration(
    connected_daq, settings, calibration
):
    """Iso DC + temperature program must convert via the calibration polynomial.

    Regression: a degenerate iso DC program like ``{"ch1": {"temp": 100}}``
    used to push the raw 100.0 directly into the AO buffer (treated as
    volts) — bypassing both ``temperature_to_voltage`` and the
    ``safe_voltage`` clamp.
    """
    from pioner.shared.modulation import ModulationParams

    # Force the pure-DC branch: amplitude=0 AND offset=0 -> enabled=False.
    settings.modulation = ModulationParams(frequency=0.0, amplitude=0.0, offset=0.0)
    calibration.theater0, calibration.theater1, calibration.theater2 = (
        -2.425, 8.0393, -0.42986,
    )
    calibration._add_params()

    iso = IsoMode(connected_daq, settings, calibration, {"ch1": {"temp": 100.0}})
    iso.arm()
    profile = iso.voltage_profiles["ch1"]
    assert profile.size == 1
    # T=100 °C should map to a voltage strictly inside the safe envelope,
    # never the raw 100.0 (= 11x safe_voltage) we used to get.
    assert 0.0 < profile[0] < calibration.safe_voltage


def test_iso_mode_stops_early_on_external_request(
    connected_daq, settings, calibration
):
    """``stop()`` from another thread must short-circuit ``run()``."""
    iso = IsoMode(
        connected_daq, settings, calibration, {"ch1": {"volt": 0.5}},
        ring_buffer_seconds=2.0,
    )
    iso.arm()

    result: dict = {}

    def _runner():
        # Long timeout so the test fails loudly if stop() does not work.
        result["df"] = iso.run(duration_seconds=10.0)

    th = threading.Thread(target=_runner)
    t0 = time.monotonic()
    th.start()
    time.sleep(0.5)
    iso.stop()
    th.join(timeout=3.0)
    elapsed = time.monotonic() - t0

    assert not th.is_alive(), "run() did not return after stop()"
    assert elapsed < 3.0, f"stop() did not interrupt in time ({elapsed:.2f}s)"
    df = result["df"]
    # Ring buffer should hold ~0.5 s worth of samples (half-buffer flip
    # granularity rounds the actual count to 0.0–1.0 s).
    assert 0 <= len(df) <= 1.5 * settings.ai_params.sample_rate


def test_iso_mode_stop_is_resettable_for_a_second_run(
    connected_daq, settings, calibration
):
    """A stale ``stop()`` from a previous run must not poison the next one."""
    iso = IsoMode(connected_daq, settings, calibration, {"ch1": {"volt": 0.5}})
    iso.arm()

    iso.stop()  # before any run
    df = iso.run(duration_seconds=1.0)
    assert len(df) > 0


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
