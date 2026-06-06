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

    def test_arm_run_fast_heat_returns_frame(self, local_controller):
        local_controller.arm_fast_heat(self._FAST)
        df = local_controller.run_fast_heat()
        assert df is not None
        for col in ("time", "Taux", "Thtr", "temp", "Uref"):
            assert col in df.columns

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

    def test_iso_run_keeps_stream_live(self, local_controller):
        # Iso drives only AO and reads AI from the persistent ring buffer
        # (P1-17, Approach C), so the live stream must NOT pause for an iso
        # run -- unlike fast/slow which still pause their finite AI scan.
        _wait_for_stream(local_controller)
        local_controller.arm_iso_mode(
            '{"ch1": {"time": [0, 1000], "volt": [0.5, 0.5]}}'
        )
        df = local_controller.run_iso_mode()
        assert local_controller.is_streaming()
        assert df is not None
        for col in ("time", "Taux", "Thtr", "temp"):
            assert col in df.columns

    def test_iso_run_streams_during_run(self, local_controller):
        # Fresh samples must keep arriving WHILE an iso run is in flight.
        import threading

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
