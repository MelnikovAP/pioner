"""Offscreen GUI regression tests for the single-window front-end (P1-29).

These run Qt under ``QT_QPA_PLATFORM=offscreen`` so they need no display and
no real DAQ. They pin the behaviours that previously only had an ad-hoc manual
smoke:

* A1 -- connect status readout (MOCK vs REAL) + disconnect reset.
* A2 -- connect-failure diagnostics (``_local_connect_error_text`` mapping).
* A3 -- idle-Thtr blanking (the heater-derived readout is only meaningful while
  a drive is active; at idle ``Rhtr = U/i`` blows up, so it must blank).
* Iso Set/Off: eternal hold drives + marks the heater, Off drives 0 V + blanks,
  Off during a run acts as Stop, and a timed program launches the worker and
  resets on completion. Plus the launch-blocking warnings (no backend / rate
  not confirmed).

Backend-dependent GUI logic is exercised with a lightweight fake controller
(records calls, no threads/ring) so the assertions are deterministic; A1 uses a
real ``LocalDeviceController`` on the mock DAQ so the backend label is genuine.
"""

import os

# Must precede any Qt import so the platform plugin is the headless one.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
import threading

import numpy as np
import pandas as pd
import pytest
from silx.gui import qt

import pioner.front.mainWindow as mw


@pytest.fixture(scope="session")
def qapp():
    """One offscreen QApplication for the whole module."""
    return qt.QApplication.instance() or qt.QApplication([])


@pytest.fixture
def recorded_errors(monkeypatch):
    """Stub the modal ``ErrorWindow`` (its ``.exec()`` would block the test).

    Returns the list of messages shown so a test can assert a warning fired.
    """
    recs: list = []
    monkeypatch.setattr(mw, "ErrorWindow", lambda *a, **k: recs.append(a[0] if a else ""))
    return recs


@pytest.fixture
def window(qapp, recorded_errors):
    """A fresh ``mainWindow`` per test; cleaned up regardless of what it did."""
    w = mw.mainWindow()
    try:
        yield w
    finally:
        # Null the run handle first so disconnect() never joins a dummy.
        w._run_thread = None
        try:
            w.stop_live_stream()
        except Exception:
            pass
        w._cancel_iso_timer()
        ctrl = w.controller
        if ctrl is not None and hasattr(ctrl, "disconnect"):
            try:
                ctrl.disconnect()
            except Exception:
                pass
        w.controller = None
        w.close()


class FakeController:
    """Minimal DeviceController stand-in: records calls, spawns no threads.

    ``run()`` blocks on a gate the test releases, so a timed-iso run can be
    observed in-flight and then completed deterministically.
    """

    backend_description = "FAKE backend"

    def __init__(self, cal_df=None):
        self.calls: list = []
        self._cal_df = cal_df
        self._gate = threading.Event()
        self.ai_sample_rate = 2000.0

    def arm_iso_mode(self, programs_json):
        self.calls.append(("arm", json.loads(programs_json)))

    def start_iso_hold(self):
        self.calls.append(("hold",))

    def stop_run(self):
        self.calls.append(("stop",))
        self._gate.set()

    def run(self):
        self.calls.append(("run",))
        self._gate.wait(5.0)
        return None

    def calibrate_window(self, data):
        return self._cal_df

    def is_streaming(self):
        return False

    def disconnect(self):
        self.calls.append(("disconnect",))


# --- A2: connect-failure diagnostics (pure static mapping) -----------------

@pytest.mark.parametrize("exc, needle", [
    (RuntimeError("No DAQ devices found on the interface"), "No DAQ device found"),
    (RuntimeError("board reports no SINGLE_ENDED channels"), "SINGLE_ENDED"),
    (OSError("libuldaq.so.1: cannot open shared object file"), "libuldaq"),
    (ValueError("something unexpected"), "Local backend failed to start"),
])
def test_local_connect_error_text(exc, needle):
    assert needle in mw.mainWindow._local_connect_error_text(exc)


# --- A1: connect status readout (MOCK vs REAL) -----------------------------

def test_local_mock_connect_sets_status_and_enables(window):
    window.sysNoHardware.setChecked(True)
    window.set_connection()
    assert window.controller is not None
    desc = window.controller.backend_description
    # Label is wired straight from backend_description (the MOCK-vs-REAL signal).
    assert window.sysStatusLabel.text() == f"Connected: {desc}"
    assert "MOCK" in desc  # the test host has no real DAQ
    assert window.experimentBox.isEnabled()
    assert window.controlTab.isEnabled()
    assert window._rate_confirmed


def test_disconnect_resets_status(window):
    window.sysNoHardware.setChecked(True)
    window.set_connection()
    window.disconnect()
    assert window.controller is None
    assert window.sysStatusLabel.text() == "Not connected"
    assert not window.experimentBox.isEnabled()
    assert window._heater_driven is False


# --- A3: idle-Thtr blanking + readout formatting ---------------------------

def test_fmt_blanks_none_and_nan():
    assert mw.mainWindow._fmt(None) == " ---"
    assert mw.mainWindow._fmt(float("nan")) == " ---"
    assert mw.mainWindow._fmt(12.345) == "12.35"


def _cal_df():
    return pd.DataFrame({"Taux": [10.0], "temp": [20.0], "Thtr": [123.0], "temp-hr": [21.0]})


def test_thtr_blanked_when_idle(window):
    window.controller = FakeController(cal_df=_cal_df())
    window._heater_driven = False
    window._update_live_values(np.zeros((4, 6)), 2000.0)
    assert window.thtrValueLabel.text() == " ---"     # heater-derived, idle -> blank
    assert window.ttplValueLabel.text() == "20.00"    # non-heater readouts still show
    assert window.tauxValueLabel.text() == "10.00"


def test_thtr_shown_when_driven(window):
    window.controller = FakeController(cal_df=_cal_df())
    window._heater_driven = True
    window._update_live_values(np.zeros((4, 6)), 2000.0)
    assert window.thtrValueLabel.text() == "123.00"


# --- Iso Set / Off -----------------------------------------------------------

def test_iso_eternal_hold_drives_and_marks(window):
    window.controller = FakeController()
    window._rate_confirmed = True
    window.setInput.setText("1.5")
    window.setDurationInput.setText("")          # empty -> eternal hold
    window.setComboBox.setCurrentText("Voltage")
    window.set_temp_volt()
    assert window._heater_driven is True
    assert ("arm", {"ch1": {"volt": 1.5}}) in window.controller.calls
    assert ("hold",) in window.controller.calls


def test_iso_off_zeroes_and_blanks(window):
    fc = FakeController()
    window.controller = fc
    window._rate_confirmed = True
    window.setInput.setText("1.5")
    window.setDurationInput.setText("")
    window.setComboBox.setCurrentText("Voltage")
    window.set_temp_volt()
    fc.calls.clear()
    window.unset_temp_volt()
    assert window._heater_driven is False
    assert ("arm", {"ch1": {"volt": 0}}) in fc.calls   # actively driven to 0 V
    assert ("hold",) in fc.calls


def test_iso_off_during_run_acts_as_stop(window):
    fc = FakeController()
    window.controller = fc
    window._run_thread = object()        # pretend a finite run is in flight
    window.unset_temp_volt()
    assert ("stop",) in fc.calls
    assert all(c[0] != "arm" for c in fc.calls)   # must NOT re-arm an iso hold
    window._run_thread = None            # so teardown doesn't treat it as live


def test_iso_timed_launches_worker_and_resets_on_finish(window, qapp):
    fc = FakeController()
    window.controller = fc
    window._rate_confirmed = True
    window.setInput.setText("0.5")
    window.setDurationInput.setText("0.05")      # 50 ms timed program
    window.setComboBox.setCurrentText("Voltage")
    window.set_temp_volt()
    # In flight: armed with a time-bounded program and a worker thread running.
    assert window._heater_driven is True
    assert window._run_thread is not None
    arm_calls = [c for c in fc.calls if c[0] == "arm"]
    assert arm_calls == [("arm", {"ch1": {"time": [0, 50], "volt": [0.5, 0.5]}})]
    # Let run() return, then pump the event loop so the finished signal lands.
    fc._gate.set()
    window._run_thread.join(timeout=5.0)
    qapp.processEvents()
    assert window._heater_driven is False        # run end -> heater no longer driven
    assert window._run_thread is None


# --- Launch-blocking guardrails ---------------------------------------------

def test_iso_set_without_backend_warns(window, recorded_errors):
    window.controller = None
    recorded_errors.clear()
    window.set_temp_volt()
    assert recorded_errors                       # an ErrorWindow was shown


def test_iso_set_without_rate_confirmed_warns(window, recorded_errors):
    fc = FakeController()
    window.controller = fc
    window._rate_confirmed = False
    window.setInput.setText("1.0")
    recorded_errors.clear()
    window.set_temp_volt()
    assert recorded_errors
    assert fc.calls == []                        # nothing armed/driven
    assert window._heater_driven is False
