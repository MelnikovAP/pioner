"""Tests for LocalDeviceController on the mock DAQ.

Exercises the controller as the GUI uses it: connect -> live stream ->
arm/run a fast-heat experiment -> get a result frame -> disconnect.
The Tango backend is not tested here (PyTango is not installable on the
CI/dev boxes); its surface is a thin pass-through to a DeviceProxy.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pytest

from pioner.back.device_controller import (
    DeviceController,
    LocalDeviceController,
)
from pioner.back.modes import read_calibrated_h5
from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH
from pioner.shared.settings import BackSettings


@pytest.fixture
def local_controller():
    settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    settings.modulation = settings.modulation.with_amplitude(0.0)  # quiet AC
    controller = LocalDeviceController(settings, ring_max_seconds=2.0)
    controller.connect()
    try:
        yield controller
    finally:
        controller.disconnect()


def _ao_shared(controller):
    """Reach the mock AO device's shared state (mock-only introspection)."""
    return controller._daq.get_ao_device()._shared  # type: ignore[union-attr]


def _wait_for_stream(controller: DeviceController, timeout: float = 2.0) -> np.ndarray:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = controller.peek_last(1000)
        if data.shape[0] > 0:
            return data
        time.sleep(0.05)
    return controller.peek_last(1000)


def _powered_window(controller, *, current=0.01, uhtr=0.41, utpl=0.55, n=1000):
    """Synthesise a raw AI window where the heater is powered (Rhtr defined).

    With the identity default calibration: ih = ch0 = ``current`` (V),
    Rhtr = (ch5 - ch0)/ih, temp = ch4*1000/gain_utpl. The chosen defaults give
    Rhtr = (0.41-0.01)/0.01 = 40 and temp = 0.55*1000/11 = 50.
    """
    channels = controller._ai_channels
    window = np.zeros((n, len(channels)), dtype=float)
    col = {ch: i for i, ch in enumerate(channels)}
    window[:, col[0]] = current   # HEATER_CURRENT_AI
    window[:, col[5]] = uhtr      # UHTR_AI
    window[:, col[4]] = utpl      # UTPL_AI -> temp
    return window


class TestRhcorr:
    """In-situ heater R-correction auto-zero wiring (P1-33)."""

    def test_report_unavailable_when_heater_not_powered(self, local_controller, monkeypatch):
        # All-zero window -> ih ~ 0 -> Rhtr NaN -> nothing to trim.
        channels = local_controller._ai_channels
        monkeypatch.setattr(
            local_controller, "peek_last",
            lambda n: np.zeros((100, len(channels)), dtype=float),
        )
        rep = local_controller.rhcorr_report()
        assert rep["available"] is False
        assert "powered" in rep["reason"]

    def test_report_previews_correction_without_mutating(self, local_controller, monkeypatch):
        monkeypatch.setattr(local_controller, "peek_last",
                            lambda n: _powered_window(local_controller))
        before = local_controller._calibration.thtrcorr
        rep = local_controller.rhcorr_report()
        assert rep["available"] is True
        assert rep["converged"] is True
        assert rep["r_op"] == pytest.approx(40.0, abs=1e-6)
        assert rep["t_target"] == pytest.approx(50.0, abs=1e-3)
        # Identity Thtr poly: corr = t_target - R = 10.
        assert rep["corr"] == pytest.approx(10.0, abs=0.01)
        # Destination is surfaced so the confirm dialog can name the overwrite.
        assert rep["target_path"]
        # Preview must NOT mutate the active calibration.
        assert local_controller._calibration.thtrcorr == before

    def test_apply_persists_and_mutates(self, local_controller, monkeypatch, tmp_path):
        import pioner.back.device_controller as dc

        out = tmp_path / "calibration.json"
        monkeypatch.setattr(dc, "CALIBRATION_FILE_REL_PATH", str(out))
        monkeypatch.setattr(local_controller, "peek_last",
                            lambda n: _powered_window(local_controller))
        rep = local_controller.apply_rhcorr()
        assert rep["available"] is True and rep["converged"] is True
        assert rep["written_to"] == str(out)
        assert local_controller._calibration.thtrcorr == pytest.approx(10.0, abs=0.01)
        # Round-trips through the written file.
        from pioner.shared.calibration import Calibration
        reloaded = Calibration()
        reloaded.read(str(out))
        assert reloaded.thtrcorr == pytest.approx(10.0, abs=0.01)


class TestChipPresence:
    """Read-only chip-presence detection wiring (P1-36)."""

    def test_report_available_on_live_stream(self, local_controller):
        _wait_for_stream(local_controller)
        report = local_controller.chip_presence_report()
        assert report["available"] is True
        # All scanned channels appear; the three candidate strategies are run.
        assert set(report["verdicts"]) == {"band", "abs_level", "variance"}
        assert report["metrics"]  # non-empty per-channel stats

    def test_chip_present_none_when_disabled(self, local_controller):
        _wait_for_stream(local_controller)
        assert local_controller._settings.chip_presence.enabled is False
        assert local_controller.chip_present() is None  # disabled -> never gates

    def test_chip_present_when_enabled(self, local_controller):
        _wait_for_stream(local_controller)
        cfg = local_controller._settings.chip_presence
        cfg.enabled = True
        cfg.strategy = "band"
        cfg.band_lo, cfg.band_hi = -1e9, 1e9      # any reading is "present"
        assert local_controller.chip_present() is True
        cfg.band_lo, cfg.band_hi = 1e8, 2e8       # impossible band -> "absent"
        assert local_controller.chip_present() is False


class TestConnection:
    def test_connects_and_streams(self, local_controller):
        assert local_controller.is_connected()
        assert local_controller.is_streaming()
        data = _wait_for_stream(local_controller)
        assert data.ndim == 2
        assert data.shape[0] > 0

    def test_disconnect_is_idempotent(self):
        settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
        controller = LocalDeviceController(settings)
        controller.connect()
        controller.disconnect()
        controller.disconnect()  # second call must not raise
        assert not controller.is_connected()
        assert not controller.is_streaming()

    def test_ai_sample_rate_reported(self, local_controller):
        assert local_controller.ai_sample_rate > 0

    def test_reports_mock_backend(self):
        # The real uldaq is absent on the dev/CI host, so the controller must
        # self-report as the mock backend. This is the truth source the GUI
        # status readout consumes to tell real-vs-mock apart (B2 / A1).
        settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
        controller = LocalDeviceController(settings)
        assert controller.is_mock is True
        assert controller.backend_description == "MOCK DAQ (no hardware)"


class TestSampleRate:
    def test_set_and_get(self, local_controller):
        local_controller.set_sample_rate(10000)
        assert local_controller.get_sample_rate() == 10000

    def test_reset_restores_file_value(self, local_controller):
        original = local_controller.get_sample_rate()
        local_controller.set_sample_rate(original + 2)
        local_controller.reset_sample_rate()
        assert local_controller.get_sample_rate() == original

    def test_rate_change_keeps_stream_alive(self, local_controller):
        # Changing an (even) rate mid-stream restarts the ring buffer but
        # must leave the stream active so the live display keeps updating.
        _wait_for_stream(local_controller)
        local_controller.set_sample_rate(10000)
        assert local_controller.is_streaming()
        data = _wait_for_stream(local_controller)
        assert data.shape[0] > 0

    # --- per-mode sample rate (P1-31) -------------------------------------

    def test_rate_for_mode_uses_per_mode_map(self, local_controller):
        assert local_controller.rate_for_mode("fast") == 20000
        assert local_controller.rate_for_mode("slow") == 2000
        assert local_controller.rate_for_mode("iso") == 2000
        # Unknown mode falls back to the default entry.
        assert local_controller.rate_for_mode("bogus") == 2000

    def test_arm_applies_mode_rate(self, local_controller):
        # Idle monitor starts at the default rate; arming fast switches the
        # active AI/AO rate to fast's configured 20 kHz.
        assert local_controller.get_sample_rate() == 2000
        local_controller.arm_fast_heat(TestExperiment._FAST)
        assert local_controller.get_sample_rate() == 20000

    def test_fast_run_restores_pre_fast_rate(self, local_controller):
        # Fast arms at 20 kHz, but after the run the ring returns to the rate
        # active before fast (the monitor default), not stays at 20 kHz.
        assert local_controller.get_sample_rate() == 2000
        local_controller.arm_fast_heat(TestExperiment._FAST)
        assert local_controller.get_sample_rate() == 20000
        local_controller.run_fast_heat()
        assert local_controller.get_sample_rate() == 2000

    def test_override_mode_rate_is_used_on_arm(self, local_controller):
        # The UI 'Apply' overrides a mode's rate for the session; a later arm
        # of that mode must pick it up.
        local_controller.override_mode_rate("slow", 4000)
        assert local_controller.rate_for_mode("slow") == 4000
        assert local_controller.get_sample_rate() == 4000

    def test_override_rejects_odd_rate(self, local_controller):
        # Odd rate breaks the 1 s half-buffer flip -> fail loud, gate not set.
        with pytest.raises(ValueError):
            local_controller.override_mode_rate("slow", 3001)

    def test_override_rejects_sub_nyquist_rate(self, local_controller):
        # f_mod = 37.5 Hz in the fixture, so 50 Hz violates rate > 2*f_mod.
        with pytest.raises(ValueError):
            local_controller.override_mode_rate("slow", 50)


class TestCalibration:
    def test_default_calibration_loaded_on_connect(self, local_controller):
        calib = local_controller.get_calibration()
        assert isinstance(calib, dict)
        assert len(calib) > 0


class TestExperiment:
    _FAST = (
        '{"ch0": {"time": [0, 1000], "volt": [0.1, 0.1]}, '
        '"ch1": {"time": [0, 250, 750, 1000], "volt": [0, 1, 1, 0]}, '
        '"ch2": {"time": [0, 1000], "volt": [5, 5]}}'
    )

    def test_arm_run_fast_heat_writes_result(self, local_controller):
        # run() returns a RunResult (paths + summary), not a frame; the data is
        # on disk -> read it back to check the engineering columns (P1-17 4c-3).
        local_controller.arm_fast_heat(self._FAST)
        result = local_controller.run_fast_heat()
        assert result is not None and result.mode == "fast" and result.rows > 0
        data = read_calibrated_h5(result.cal_path)
        for col in ("time", "Taux", "Thtr", "temp", "Uref"):
            assert col in data

    def test_run_without_arm_returns_none(self, local_controller):
        assert local_controller.run() is None

    def test_stream_resumes_after_experiment(self, local_controller):
        _wait_for_stream(local_controller)
        local_controller.arm_fast_heat(self._FAST)
        local_controller.run_fast_heat()
        # Stream must be active again after the run finishes.
        assert local_controller.is_streaming()
        data = _wait_for_stream(local_controller)
        assert data.shape[0] > 0

    def test_slow_run_streams_off_ring_and_writes_paths(
        self, local_controller, tmp_path, monkeypatch
    ):
        # Redirect the result file into tmp so data/exp_data.h5 is untouched.
        import pioner.back.device_controller as dc
        monkeypatch.setattr(dc, "EXP_DATA_FILE_REL_PATH", str(tmp_path / "exp.h5"))

        _wait_for_stream(local_controller)
        local_controller.arm(
            "slow",
            '{"ch0": {"time": [0, 500], "volt": [0.1, 0.1]}, '
            '"ch1": {"time": [0, 500], "volt": [0, 1]}}',
        )
        result = local_controller.run()
        # Off-ring: the live stream must NOT pause for slow.
        assert local_controller.is_streaming()
        assert result is not None and result.mode == "slow" and result.rows > 0
        # Result lives on disk in two files (raw U + calibrated T), distinct.
        assert result.raw_path is not None and result.raw_path != result.cal_path
        import os
        assert os.path.exists(result.cal_path) and os.path.exists(result.raw_path)
        data = read_calibrated_h5(result.cal_path)
        for col in ("time", "temp", "Thtr"):
            assert col in data

    def test_slow_run_stop_aborts_and_zeroes(
        self, local_controller, tmp_path, monkeypatch
    ):
        # Stop mid slow streaming -> RunResult.aborted, heater zeroed, partial
        # data finalised, and the live stream still alive (off-ring).
        import pioner.back.device_controller as dc
        import threading

        monkeypatch.setattr(dc, "EXP_DATA_FILE_REL_PATH", str(tmp_path / "exp.h5"))
        _wait_for_stream(local_controller)
        local_controller.arm(
            "slow",
            '{"ch0": {"time": [0, 5000], "volt": [0.1, 0.1]}, '
            '"ch1": {"time": [0, 5000], "volt": [0, 1]}}',
        )
        holder: dict = {}

        def _go():
            holder["r"] = local_controller.run()

        t = threading.Thread(target=_go)
        t.start()
        time.sleep(0.6)
        local_controller.stop_run()
        t.join(timeout=4.0)        # 5 s ramp; only passes if the abort worked

        assert not t.is_alive(), "slow streaming run did not stop"
        result = holder["r"]
        assert result is not None and result.aborted
        assert _ao_shared(local_controller).iso_voltages.get(1) == 0.0  # heater off
        assert local_controller.is_streaming()                          # off-ring

    def test_iso_finite_run_streams_off_ring_and_writes_paths(
        self, local_controller, tmp_path, monkeypatch
    ):
        # Finite iso experiment (P1-17 step 5): off-ring streaming like slow, so
        # the live stream must NOT pause; the result is on disk (raw U + cal T).
        import pioner.back.device_controller as dc
        monkeypatch.setattr(dc, "EXP_DATA_FILE_REL_PATH", str(tmp_path / "exp.h5"))
        _wait_for_stream(local_controller)
        local_controller.arm_iso_mode(
            '{"ch1": {"time": [0, 1000], "volt": [0.5, 0.5]}}'
        )
        result = local_controller.run_iso_mode()
        assert local_controller.is_streaming()
        assert result is not None and result.mode == "iso" and result.rows > 0
        assert result.raw_path is not None and result.raw_path != result.cal_path
        import os
        assert os.path.exists(result.cal_path) and os.path.exists(result.raw_path)
        data = read_calibrated_h5(result.cal_path)
        for col in ("time", "Taux", "Thtr", "temp"):
            assert col in data
        # Iso AO is a constant hold -> Uref is tiled (constant), never NaN.
        assert np.all(np.isfinite(data["Uref"]))

    def test_iso_run_streams_during_run(self, local_controller, tmp_path, monkeypatch):
        # Fresh samples must keep arriving WHILE an iso run is in flight.
        import threading

        import pioner.back.device_controller as dc
        monkeypatch.setattr(dc, "EXP_DATA_FILE_REL_PATH", str(tmp_path / "exp.h5"))
        _wait_for_stream(local_controller)
        local_controller.arm_iso_mode(
            '{"ch1": {"time": [0, 2000], "volt": [0.5, 0.5]}}'
        )
        done = threading.Event()

        def _go():
            local_controller.run_iso_mode()
            done.set()

        worker = threading.Thread(target=_go)
        worker.start()
        try:
            seen_active = []
            # peek_last has no cursor, so probing here does not disturb the
            # run's own read_new cursor; a non-empty window each tick proves
            # the persistent scan keeps producing data during the run.
            seen_rows = []
            for _ in range(6):
                time.sleep(0.2)
                seen_active.append(local_controller.is_streaming())
                seen_rows.append(local_controller.peek_last(200).shape[0])
        finally:
            worker.join(timeout=5.0)
        assert all(seen_active), seen_active
        assert all(r > 0 for r in seen_rows), seen_rows


class TestIsoHold:
    """Eternal iso hold (P1-5): start_iso_hold drives AO and returns at once,
    AI keeps streaming, stop_run halts the hold."""

    def test_start_iso_hold_is_nonblocking_and_holds(self, local_controller):
        local_controller.arm("iso", json.dumps({"ch1": {"volt": 0.5}}))
        t0 = time.monotonic()
        local_controller.start_iso_hold()
        elapsed = time.monotonic() - t0
        # Returns immediately -- it must NOT block for the legacy ~1 s run.
        assert elapsed < 0.5, f"start_iso_hold blocked for {elapsed:.2f}s"
        assert local_controller.is_holding is True
        # The persistent AI stream stays alive during the hold.
        assert local_controller.is_streaming()
        data = _wait_for_stream(local_controller)
        assert data.shape[0] > 0
        local_controller.stop_run()
        assert local_controller.is_holding is False
        # AI is untouched by stopping the AO hold.
        assert local_controller.is_streaming()

    def test_start_iso_hold_requires_armed_iso(self, local_controller):
        with pytest.raises(RuntimeError):
            local_controller.start_iso_hold()  # nothing armed

    def test_stop_run_zeroes_heater_after_hold(self, local_controller):
        # Aborting a hold must drive the heater to 0 V (not just stop the
        # scan, which would latch the setpoint and leave the chip powered).
        local_controller.arm("iso", json.dumps({"ch1": {"volt": 0.5}}))
        local_controller.start_iso_hold()
        local_controller.stop_run()
        assert local_controller.is_holding is False
        shared = _ao_shared(local_controller)
        assert shared.iso_voltages.get(1) == 0.0

    def test_disconnect_zeroes_heater_after_hold(self):
        # A clean system-off (disconnect) while holding must leave AO at 0 V.
        settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
        settings.modulation = settings.modulation.with_amplitude(0.0)
        controller = LocalDeviceController(settings)
        controller.connect()
        controller.arm("iso", json.dumps({"ch1": {"volt": 0.5}}))
        controller.start_iso_hold()
        shared = _ao_shared(controller)
        controller.disconnect()
        # zero_ao ran before release, so the last commanded heater value is 0.
        assert shared.iso_voltages.get(1) == 0.0
