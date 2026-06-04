"""Tests for LocalDeviceController on the mock DAQ.

Exercises the controller as the GUI uses it: connect -> live stream ->
arm/run a fast-heat experiment -> get a result frame -> disconnect.
The Tango backend is not tested here (PyTango is not installable on the
CI/dev boxes); its surface is a thin pass-through to a DeviceProxy.
"""

from __future__ import annotations

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
