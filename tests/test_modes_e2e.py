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
    SafeVoltageError,
    SlowMode,
    create_mode,
)
from pioner.shared.modulation import ModulationParams
from pioner.shared.settings import ExperimentLimits


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


def test_slow_mode_amplitude_correction_divides_reported_amplitude(
    connected_daq, settings, calibration, fast_programs
):
    """P1-32: with amplitude correction enabled, the reported temp-hr_amp is
    divided by kamp(Thtr). Single run (mock AI is not bit-identical across
    runs): the unchanged temp-hr column lets us recompute the *uncorrected*
    amplitude with the same lock-in and confirm the divider on every
    finite-Thtr sample. Constant kamp=2 makes it an exact halving."""
    from pioner.shared.modulation import lockin_demodulate

    programs = {
        "ch0": {"time": [0, 2000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 2000], "volt": [0, 1]},
    }
    settings.modulation = settings.modulation.with_amplitude(0.1)
    # Constant kamp(T) = 2, opted in.
    calibration.ac0, calibration.ac1, calibration.ac2, calibration.ac3 = 2.0, 0.0, 0.0, 0.0
    calibration.amplitude_correction_enabled = True

    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    df = mode.run()

    # Recompute the uncorrected amplitude from the (untouched) temp-hr column.
    raw_amp, _ = lockin_demodulate(
        df["temp-hr"].to_numpy(),
        sample_rate=settings.ai_params.sample_rate,
        frequency=settings.modulation.frequency,
    )
    reported = df["temp-hr_amp"].to_numpy()
    finite = np.isfinite(reported) & np.isfinite(df["Thtr"].to_numpy())
    assert finite.sum() > 0, "no finite-Thtr samples to compare"
    np.testing.assert_allclose(reported[finite], raw_amp[finite] / 2.0, rtol=1e-9)


def test_slow_mode_measured_reference_runs_and_produces_phase(
    connected_daq, settings, calibration, fast_programs
):
    """P1-34 wiring smoke: a slow run with the measured-reference flag on
    completes and still produces the lock-in phase column (the reference is
    AI ch0; the phase math itself is unit-tested in test_modulation)."""
    programs = {
        "ch0": {"time": [0, 2000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 2000], "volt": [0, 1]},
    }
    settings.modulation = ModulationParams(
        frequency=settings.modulation.frequency, amplitude=0.1, offset=0.0,
        use_measured_reference=True,
    )
    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    df = mode.run()
    assert "temp-hr_phase" in df.columns
    assert "temp-hr_amp" in df.columns


# --- P1-4: fail-loud heater over-voltage block at arm -----------------------

def test_arm_blocks_raw_volt_over_safe_voltage(connected_daq, settings, calibration):
    """A raw volt program whose heater peak exceeds safe_voltage is rejected
    fail-loud at arm (no silent clamp)."""
    programs = {
        "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 1000], "volt": [0.0, calibration.safe_voltage + 1.0]},
    }
    mode = FastHeat(connected_daq, settings, calibration, programs)
    with pytest.raises(SafeVoltageError):
        mode.arm()


def test_arm_blocks_temp_over_chip_ceiling(connected_daq, settings, calibration):
    """A temperature above the chip ceiling (max_temp = T(safe_voltage)) is
    rejected fail-loud. Limits are widened so the safe_voltage check is what fires."""
    settings.limits_by_mode = {"fast": ExperimentLimits(min_temp=0.0, max_temp=1e6)}
    too_hot = calibration.max_temp + 100.0
    programs = {
        "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 1000], "temp": [20.0, too_hot]},
    }
    mode = FastHeat(connected_daq, settings, calibration, programs)
    with pytest.raises(SafeVoltageError):
        mode.arm()


def test_arm_blocks_modulation_peak_over_safe_voltage(connected_daq, settings, calibration):
    """DC near safe_voltage + AC amplitude pushes the modulated peak over the
    envelope -> fail-loud at arm rather than a silently flat-topped sine."""
    settings.modulation = ModulationParams(frequency=100.0, amplitude=2.0, offset=0.0)
    dc = calibration.safe_voltage - 0.5  # static peak is fine; +2 V AC is not
    programs = {
        "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 1000], "volt": [dc, dc]},
    }
    mode = SlowMode(connected_daq, settings, calibration, programs)
    with pytest.raises(SafeVoltageError):
        mode.arm()


def test_arm_accepts_program_within_safe_voltage(connected_daq, settings, calibration):
    """Sanity: a heater volt program within safe_voltage arms cleanly."""
    programs = {
        "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 1000], "volt": [0.0, calibration.safe_voltage - 1.0]},
    }
    mode = FastHeat(connected_daq, settings, calibration, programs)
    mode.arm()
    assert mode.is_armed()


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


def test_validate_accepts_non_second_durations(
    connected_daq, settings, calibration
):
    # The whole-second (total_ms % 1000 == 0) constraint was lifted; arming a
    # fractional-duration program must no longer raise.
    prog = {"ch1": {"time": [0, 1500], "volt": [0, 1]}}
    FastHeat(connected_daq, settings, calibration, prog).arm()


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


def test_fast_mode_fractional_seconds(connected_daq, settings, calibration):
    """Non-integer-second durations are allowed (1s buffer constraint lifted):
    the collected frame is trimmed to round(sample_rate * total_s)."""
    settings.modulation = settings.modulation.with_amplitude(0.0)
    rate = settings.ai_params.sample_rate
    for total_ms in (500, 1500):
        programs = {
            "ch0": {"time": [0, total_ms], "volt": [0.1, 0.1]},
            "ch1": {"time": [0, total_ms], "volt": [0, 1]},
        }
        mode = FastHeat(connected_daq, settings, calibration, programs)
        mode.arm()
        df = mode.run()
        expected = int(round(rate * total_ms / 1000.0))
        assert len(df) == expected, f"{total_ms} ms -> {len(df)} != {expected}"


def test_clip_modulation_warns_when_clipped(caplog):
    import logging
    from pioner.back.modes import _clip_modulation_to_safe
    arr = np.array([8.0, 10.0, 8.0, -1.0])  # exceeds safe=9 V and dips below 0
    with caplog.at_level(logging.WARNING):
        _clip_modulation_to_safe(arr, 9.0, "ch1")
    assert "clipped" in caplog.text, "silent clip -- P1-4 warning missing"
    assert arr.max() <= 9.0 and arr.min() >= 0.0


def test_clip_modulation_silent_when_within_range(caplog):
    import logging
    from pioner.back.modes import _clip_modulation_to_safe
    arr = np.array([0.5, 8.9, 0.1])
    with caplog.at_level(logging.WARNING):
        _clip_modulation_to_safe(arr, 9.0, "ch1")
    assert "clipped" not in caplog.text


def test_zero_ao_drives_all_channels_to_zero(connected_daq, settings):
    """Safety: zero_ao must drive every configured AO channel to 0 V so the
    heater is not left latched at its last value on disconnect/abort."""
    from pioner.back.experiment_manager import ExperimentManager

    em = ExperimentManager(connected_daq, settings)
    em.ao_set(1, 0.5)
    shared = connected_daq.get_ao_device()._shared
    assert shared.iso_voltages.get(1) == 0.5  # sanity: drive applied

    em.zero_ao()
    for ch in range(settings.ao_params.low_channel, settings.ao_params.high_channel + 1):
        assert shared.iso_voltages.get(ch) == 0.0, f"AO ch{ch} not zeroed"


def test_finite_scan_single_shot_full_buffer(connected_daq, settings):
    """Fast-heat single-shot DEFAULTIO path (P1-30): full-length host buffer,
    read once at the end, exact sample count for whole and fractional seconds."""
    from pioner.back.experiment_manager import ExperimentManager

    rate = settings.ai_params.sample_rate
    ai_channels = list(range(settings.ai_params.low_channel,
                             settings.ai_params.high_channel + 1))
    for secs in (1.0, 1.5):
        n = int(round(rate * secs))
        em = ExperimentManager(connected_daq, settings)
        profiles = {"ch1": np.linspace(0.0, 1.0, n).tolist()}
        result = em.finite_scan(profiles, ai_channels, seconds=secs, single_shot=True)
        assert len(result.data) == n, f"{secs}s -> {len(result.data)} != {n}"
        assert list(result.data.columns) == ai_channels


# --- interruptible run + Stop (P1-17 step 3) -------------------------------

def test_slow_mode_stop_cancels_and_zeroes(connected_daq, settings, calibration):
    """A Stop mid-run (CONTINUOUS path) aborts the collect loop, returns a
    short frame, and drives the heater to 0 V (heater-safety rule)."""
    settings.modulation = settings.modulation.with_amplitude(0.0)  # no lock-in
    rate = settings.ai_params.sample_rate
    programs = {
        "ch0": {"time": [0, 5000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 5000], "volt": [0, 1]},
    }
    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    holder: dict = {}

    def _run():
        holder["df"] = mode.run()

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.8)          # let at least one half-buffer (0.5 s) collect
    mode.stop()
    t.join(timeout=3.0)

    assert not t.is_alive(), "run did not stop after mode.stop()"
    shared = connected_daq.get_ao_device()._shared
    assert shared.iso_voltages.get(1) == 0.0, "heater (ch1) not zeroed on abort"
    df = holder["df"]
    assert df is not None and 0 < len(df) < rate * 5, (
        f"expected a short (cancelled) frame, got {None if df is None else len(df)}"
    )


def test_fast_mode_stop_returns_early_and_zeroes(connected_daq, settings, calibration):
    """A Stop mid-run (single-shot path) returns well before the full duration
    and zeroes the heater. The single-shot buffer is full-length, so the frame
    length is not the signal here -- the early return is."""
    settings.modulation = settings.modulation.with_amplitude(0.0)
    programs = {
        "ch0": {"time": [0, 3000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 3000], "volt": [0, 1]},
    }
    mode = FastHeat(connected_daq, settings, calibration, programs)
    mode.arm()
    holder: dict = {}

    def _run():
        holder["df"] = mode.run()

    t = threading.Thread(target=_run)
    t.start()
    time.sleep(0.4)
    mode.stop()
    t.join(timeout=2.0)      # < 3 s nominal: only passes if the abort worked

    assert not t.is_alive(), "fast run did not stop early after mode.stop()"
    shared = connected_daq.get_ao_device()._shared
    assert shared.iso_voltages.get(1) == 0.0, "heater (ch1) not zeroed on abort"


def test_mode_stop_without_run_is_noop(connected_daq, settings, calibration):
    """stop() before any run() is a harmless no-op (no active ExperimentManager)."""
    programs = {"ch1": {"time": [0, 1000], "volt": [0, 1]}}
    mode = FastHeat(connected_daq, settings, calibration, programs)
    mode.arm()
    mode.stop()  # must not raise


# --- slow off-ring: injected ring + snapshot (P1-17 step 4b) ----------------

def test_slow_mode_injected_off_ring(connected_daq, settings, calibration):
    """Injected path: SlowMode drives only AO and reads AI from a caller-supplied
    snapshot (the persistent ring), never starting its own AI scan. The frame is
    calibrated and trimmed to the ramp length."""
    from pioner.back.experiment_manager import ExperimentManager

    settings.modulation = settings.modulation.with_amplitude(0.0)  # no lock-in
    rate = settings.ai_params.sample_rate
    programs = {
        "ch0": {"time": [0, 400], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 400], "volt": [0, 1]},
    }
    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    total = int(round(rate * 0.4))
    # Snapshot returns MORE rows than the ramp -> must be trimmed to `total`
    # (else apply_calibration would tile Uref, wrong for a ramp).
    fake = np.random.default_rng(0).uniform(0.0, 1.0,
                                            size=(total + 64, len(DEFAULT_AI_CHANNELS)))
    with ExperimentManager(connected_daq, settings) as em:
        df = mode.run(em=em, snapshot=lambda: fake)
    assert len(df) == total
    for col in ("time", "Taux", "Thtr", "temp", "Uref"):
        assert col in df.columns


def test_slow_mode_injected_stop_interrupts(connected_daq, settings, calibration):
    """stop() interrupts the injected ramp wait promptly (no own scan to cancel,
    so it must be the _stop_event path)."""
    from pioner.back.experiment_manager import ExperimentManager

    settings.modulation = settings.modulation.with_amplitude(0.0)
    programs = {
        "ch0": {"time": [0, 5000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 5000], "volt": [0, 1]},
    }
    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    holder: dict = {}
    with ExperimentManager(connected_daq, settings) as em:
        def _run():
            holder["df"] = mode.run(
                em=em,
                snapshot=lambda: np.zeros((10, len(DEFAULT_AI_CHANNELS))),
            )
        t = threading.Thread(target=_run)
        t.start()
        time.sleep(0.2)
        mode.stop()
        t.join(timeout=2.0)        # 5 s ramp; only passes if stop interrupted it
        assert not t.is_alive(), "injected slow run did not stop"
    assert "df" in holder


# --- experiment limits validation (step 8 / P1-38) -------------------------

def test_arm_rejects_temperature_above_max(connected_daq, settings, calibration):
    from pioner.shared.settings import ExperimentLimits
    # arm() reads this mode's per-mode limit set; override "slow" for isolation.
    settings.limits_by_mode = {"slow": ExperimentLimits(min_temp=0.0, max_temp=300.0)}
    programs = {"ch1": {"time": [0, 1000], "temp": [20, 400]}}  # 400 C > 300
    mode = SlowMode(connected_daq, settings, calibration, programs)
    with pytest.raises(ValueError):
        mode.arm()


def test_arm_accepts_heat_iso_cool_in_range(connected_daq, settings, calibration):
    from pioner.shared.settings import ExperimentLimits
    settings.limits_by_mode = {"slow": ExperimentLimits(min_temp=0.0, max_temp=300.0)}
    settings.modulation = settings.modulation.with_amplitude(0.0)
    # heat (20->200) / iso (200) / cool (200->20), all within [0, 300] C.
    programs = {"ch1": {"time": [0, 100, 200, 300], "temp": [20, 200, 200, 20]}}
    mode = SlowMode(connected_daq, settings, calibration, programs)
    mode.arm()
    assert mode.is_armed()


def test_arm_rejects_cool_faster_than_max(connected_daq, settings, calibration):
    from pioner.shared.settings import ExperimentLimits
    # 10 K/s max passive cool; the cool segment 200->20 over 100 ms = 1800 K/s.
    settings.limits_by_mode = {
        "slow": ExperimentLimits(min_temp=0.0, max_temp=300.0, max_cool_rate=10.0)
    }
    programs = {"ch1": {"time": [0, 100, 200], "temp": [20, 200, 20]}}
    mode = SlowMode(connected_daq, settings, calibration, programs)
    with pytest.raises(ValueError):
        mode.arm()


def test_arm_rejects_heat_slower_than_min(connected_daq, settings, calibration):
    from pioner.shared.settings import ExperimentLimits
    # 50 K/s min heat; the heat segment 20->40 over 1000 ms = 20 K/s is too slow.
    settings.limits_by_mode = {
        "slow": ExperimentLimits(min_temp=0.0, max_temp=300.0, min_heat_rate=50.0)
    }
    programs = {"ch1": {"time": [0, 1000], "temp": [20, 40]}}
    mode = SlowMode(connected_daq, settings, calibration, programs)
    with pytest.raises(ValueError):
        mode.arm()


# --- multi-segment program builder core (P1-39) ----------------------------

def test_segments_to_program_heat_iso_cool():
    from pioner.back.modes import segments_to_program
    prog = segments_to_program([
        {"type": "heat", "target": 200, "duration_ms": 100},
        {"type": "iso", "duration_ms": 100},
        {"type": "cool", "target": 20, "duration_ms": 100},
    ], start_temp=20.0)
    assert prog["time"] == [0.0, 100.0, 200.0, 300.0]
    assert prog["temp"] == [20.0, 200.0, 200.0, 20.0]   # iso holds 200


def test_segments_to_program_rejects_bad_segments():
    from pioner.back.modes import segments_to_program
    import pytest as _pytest
    with _pytest.raises(ValueError):
        segments_to_program([{"type": "heat", "target": 10, "duration_ms": 100}], start_temp=50.0)  # heat below current
    with _pytest.raises(ValueError):
        segments_to_program([{"type": "cool", "target": 90, "duration_ms": 100}], start_temp=50.0)  # cool above current
    with _pytest.raises(ValueError):
        segments_to_program([{"type": "bogus", "duration_ms": 100}])
    with _pytest.raises(ValueError):
        segments_to_program([{"type": "iso", "duration_ms": 0}])


def test_arm_rejects_nonfinite_program(connected_daq, settings, calibration):
    """A program with NaN/Inf is rejected fail-loud at construction (P2-18)."""
    bad = {"ch1": {"time": [0, 1000], "temp": [20.0, float("nan")]}}
    with pytest.raises(ValueError, match="NaN/Inf"):
        FastHeat(connected_daq, settings, calibration, bad)


def test_scan_data_generator_logs_absent_channel(caplog):
    """An AO channel with no profile is held at 0 V and logged (P1-12)."""
    import logging

    from pioner.back.ao_data_generators import ScanDataGenerator
    with caplog.at_level(logging.INFO, logger="pioner.back.ao_data_generators"):
        ScanDataGenerator({"ch0": [0.1, 0.1]}, low_channel=0, high_channel=1)
    assert any("ch1" in r.message and "0 V" in r.message for r in caplog.records)
