"""Main window of the PIONER GUI.

Mode selection (``modeComboBox``: Fast / Slow / Iso) drives the unified
``DeviceController.arm(mode_name, programs_json)`` / ``run`` pair. Fast and
slow share the ramp-table editor (``fh_arm`` / ``fh_run``); slow layers AC
modulation on top in the backend, configured from the Modulation block
(Frequency / Amplitude / Offset) which feeds ``BackSettings.modulation`` and
:class:`pioner.back.modes.SlowMode`. Iso uses the Set/Off controls
(``set_temp_volt`` / ``unset_temp_volt``) for static set-and-hold; the
backend streams it live against the persistent ring buffer.

Not wired here yet: a dedicated CalibrationMode (todo P1-22) -- calibration
today is the separate ``calibWindow`` file-apply flow, not a run mode.
"""

import json
import logging
import os
import shutil
import threading
from typing import Any, Optional

import numpy as np
import pandas as pd
from silx.gui import qt

from pioner.back.device_controller import (
    DeviceController,
    LocalDeviceController,
    TangoDeviceController,
)
from pioner.back.modes import read_calibrated_h5
from pioner.front.calibWindow import *
from pioner.front.configWindow import *
from pioner.front.mainWindowUi import mainWindowUi
from pioner.front.messageWindows import *
from pioner.front.scope_controls import ScopeControls, downsample_for_display
from pioner.shared.channels import HEATER_AO
from pioner.shared.constants import *
from pioner.shared.modulation import fft_demodulate
from pioner.shared.settings import BackSettings, FrontSettings, UISettings
from pioner.shared.utils import Dict2Class


logger = logging.getLogger(__name__)


class _RunWorker(qt.QObject):
    """Runs ``DeviceController.run()`` off the GUI thread (P1-17 step 7).

    ``run()`` can block for the whole experiment (slow / finite-iso last minutes
    to hours); doing it on a worker keeps the GUI responsive and lets Stop fire
    mid-run. The ``finished`` signal carries the ``RunResult`` (or ``None``) back
    to the main thread (queued connection), where the result is plotted.
    """

    finished = qt.Signal(object)

    def __init__(self, controller):
        super().__init__()
        self._controller = controller

    def run(self):
        result = None
        try:
            result = self._controller.run()
        except Exception:
            logger.exception("Experiment run failed on the worker thread")
        self.finished.emit(result)


def _relative_if_under_cwd(path: str) -> str:
    """Return ``path`` as a './'-prefixed relative path if it sits under cwd,
    otherwise the absolute form. Keeps settings.json portable across machines
    when paths point inside the project tree."""
    abs_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    try:
        rel = os.path.relpath(abs_path, cwd)
    except ValueError:
        return abs_path
    if rel.startswith(".."):
        return abs_path
    return os.path.join(".", rel)


class mainWindow(mainWindowUi):
    def __init__(self, parent=None):
        super(mainWindow, self).__init__(parent)

        # Backend handle. ``None`` until ``set_connection`` builds either a
        # LocalDeviceController (in-process DAQ / mock) or a
        # TangoDeviceController (legacy network path). Runtime ``None``
        # checks guard every call site that needs the wire.
        self.controller: Optional[DeviceController] = None
        # True while the operator has commanded a sustained heater drive (iso
        # Set / hold). The live Thtr readout is only meaningful while a drive is
        # active; at idle the heater-current proxy is ~0 so Rhtr=U/i blows up
        # (the ~-1071 sentinel, todo P0-3), hence Thtr is blanked unless this
        # is set. With the iso-hold rewire (P1-5) a hold genuinely sustains AO,
        # so a live tick now does coincide with a real drive.
        self._heater_driven: bool = False
        # Single-shot timer for a timed iso program (auto-Off after N seconds).
        self._iso_timer: Optional[Any] = None
        # Apply gate (P1-31): changing the mode moves the per-mode sample rate
        # into an unconfirmed state; the experiment-launch buttons stay disabled
        # until the operator presses Apply (or Reset) to confirm it.
        self._rate_confirmed: bool = True
        # Background experiment run (P1-17 step 7): fast/slow/iso runs execute on
        # a worker thread so the GUI stays responsive (and Stop works) for the
        # whole duration instead of freezing inside a blocking run().
        self._run_thread: Optional[Any] = None
        self._run_worker: Optional[Any] = None
        self.preload_settings()

        self.sysOnButton.clicked.connect(self.sysOnButtonPressed)
        self.sysOffButton.clicked.connect(self.disconnect)
        self.sysDataPathButton.clicked.connect(self.select_data_path)
        self.sysSetupButton.clicked.connect(self.show_help)

        self.calibPathButton.clicked.connect(self.select_calibration_file)
        self.calibViewButton.clicked.connect(self.view_calibraton_info)
        self.calibApplyButton.clicked.connect(self.apply_calib)

        self.applyScanSampleRateButton.clicked.connect(self.apply_sample_rate)
        self.resetScanSampleRateButton.clicked.connect(self.reset_sample_rate)

        self.applyModulationParamsButton.clicked.connect(self.apply_modulation_params)
        self.resetModulationParamsButton.clicked.connect(self.reset_modulation_params)

        self.armButton.clicked.connect(self.fh_arm)
        self.startButton.clicked.connect(self.fh_run)
        self.stopButton.clicked.connect(self.fh_stop)
        self.stopButton.setEnabled(False)  # enabled only while a run is in flight

        self.setTempVoltButton.clicked.connect(self.set_temp_volt)
        self.unsetTempVoltButton.clicked.connect(self.unset_temp_volt)

        self.modeComboBox.currentIndexChanged.connect(self._on_mode_changed)
        self._on_mode_changed()  # apply initial visibility (Fast)

# for debugging
        self.terror0Button.clicked.connect(self.print_debug)

        self._init_live_stream()

    # ===================================
    # Live streaming (Signals tab)
    # ===================================
    @staticmethod
    def _pick_ui_settings_path() -> str:
        if os.path.exists(UI_SETTINGS_FILE_REL_PATH):
            return UI_SETTINGS_FILE_REL_PATH
        return DEFAULT_UI_SETTINGS_FILE_REL_PATH

    def _init_live_stream(self):
        """Set up the Signals-tab scope controls + refresh timer.

        Layout is left to mainWindowUi; we only append a compact scope
        control strip under the existing (previously unused) signalsPlot.
        """
        self._ui_settings = UISettings(self._pick_ui_settings_path())
        self.scopeControls = ScopeControls(self._ui_settings, self)
        # signalsTab's layout is set in mainWindowUi (setLayout), so it is
        # never None here; assert for the type-checker and fail loud if the
        # Ui is ever changed to drop it.
        signals_layout = self.signalsTab.layout()
        assert signals_layout is not None, "signalsTab has no layout (mainWindowUi)"
        signals_layout.addWidget(self.scopeControls)
        self.scopeControls.changed.connect(self._on_scope_changed)
        self._apply_signal_plot_limits()

        self._live_timer = qt.QTimer(self)
        self._live_timer.setInterval(self._ui_settings.refresh_interval_ms)
        self._live_timer.timeout.connect(self._live_tick)

    def _apply_signal_plot_limits(self):
        plot = self.signalsPlot.resultPlot
        x_scale = self.scopeControls.x_scale_seconds()
        y_span = self.scopeControls.y_span_volts()
        midpoint = (self._ui_settings.y_min + self._ui_settings.y_max) / 2.0
        plot.getXAxis().setLimits(0.0, x_scale)
        plot.getYAxis().setLimits(midpoint - y_span / 2.0, midpoint + y_span / 2.0)

    def _on_scope_changed(self):
        # Drop curves for channels the operator just disabled.
        for ch_idx, label in self._ui_settings.channel_labels.items():
            if not self.scopeControls.channel_enabled(ch_idx):
                self.signalsPlot.resultPlot.removeCurve(label)
        self._apply_signal_plot_limits()

    def start_live_stream(self):
        if self.controller is None or not self.controller.is_streaming():
            return
        self.controlTabsWidget.setCurrentIndex(0)  # show Signals tab
        self._live_timer.start()

    def stop_live_stream(self):
        if hasattr(self, "_live_timer"):
            self._live_timer.stop()

    def _live_tick(self):
        if self.controller is None:
            return
        sample_rate = self.controller.ai_sample_rate
        if sample_rate <= 0:
            return
        x_scale = self.scopeControls.x_scale_seconds()
        x_shift = self.scopeControls.x_shift_seconds()
        window_samples = int(round(x_scale * sample_rate))
        shift_samples = int(round(x_shift * sample_rate))
        data = self.controller.peek_last(window_samples + shift_samples)
        if data.size == 0:
            return
        if shift_samples > 0 and data.shape[0] > shift_samples:
            data = data[:-shift_samples]
        if data.size == 0:
            return
        self._draw_live_signals(data, sample_rate)
        self._update_live_values(data, sample_rate)

    def _draw_live_signals(self, data, sample_rate):
        display = downsample_for_display(data, self._ui_settings.max_plot_points)
        n = display.shape[0]
        dt = data.shape[0] / sample_rate / max(n, 1)
        x = np.arange(n) * dt
        for ch_idx in sorted(self._ui_settings.channel_labels):
            if not self.scopeControls.channel_enabled(ch_idx):
                continue
            if ch_idx >= display.shape[1]:
                continue
            self.signalsPlot.resultPlot.addCurve(
                x, display[:, ch_idx],
                legend=self._ui_settings.channel_labels[ch_idx],
                color=self._ui_settings.channel_colors.get(ch_idx, "#000000"),
                resetzoom=False,
            )

    def _update_live_values(self, data, sample_rate):
        # Engineering-unit readout via the controller's calibration.
        calibrate = getattr(self.controller, "calibrate_window", None)
        if calibrate is not None:
            try:
                cal = calibrate(data)
            except Exception:
                cal = None
            if cal is not None and not cal.empty:
                last = cal.iloc[-1]
                self.tauxValueLabel.setText(self._fmt(last.get("Taux")))
                self.ttplValueLabel.setText(self._fmt(last.get("temp")))
                # Thtr is heater-derived (Rhtr = U/i); only meaningful while a
                # drive is active. During an iso hold the AO genuinely sustains
                # the heater, so show it; at idle i ~ 0 makes Rhtr blow up to
                # the ~-1071 sentinel (todo P0-3), so blank it.
                thtr = last.get("Thtr") if self._heater_driven else None
                self.thtrValueLabel.setText(self._fmt(thtr))
                self.thtrdynValueLabel.setText(self._fmt(last.get("temp-hr")))

        # Modulation frequency + Umod amplitude via FFT demod.
        freq = float(self.settings.modulation_frequency)
        self.frequencyValueLabel.setText(f"{freq:.1f}")
        if freq > 0 and data.shape[1] >= 2:
            samples_per_period = sample_rate / freq
            if data.shape[0] >= int(samples_per_period):
                try:
                    result = fft_demodulate(
                        data[:, 1], sample_rate=sample_rate,
                        frequency=freq, harmonics=(1,),
                    )
                    self.umodhtrValueLabel.setText(
                        f"{result.fundamental.amplitude * 1000.0:.3f}")
                except ValueError:
                    pass

    @staticmethod
    def _fmt(value) -> str:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return " ---"
        return f"{float(value):.2f}"

    def print_debug(self):
        print(self.settings.sample_rate)
        calibration = getattr(self, "calibration", None)
        print(calibration.comment if calibration is not None else "no calibration loaded")
# end for debugging
    
    def sysOnButtonPressed(self):
        self.set_connection()

    def set_connection(self):
        # Backend choice: the "run without hardware" checkbox selects the
        # in-process LocalDeviceController, which talks to the real MCC
        # board when present and the pure-Python mock otherwise (see
        # ``mock_uldaq.DAQ_AVAILABLE``). Unchecked selects the legacy Tango
        # network path. Either way the GUI only sees a DeviceController.
        if self.sysNoHardware.isChecked():
            self._connect_local()
            return
        try:
            self.controller = TangoDeviceController(self.settings)
            self.controller.connect()
            self._after_connect()
        except Exception:
            error_text = ("No connection to the device or\nTANGO module not found!\n"
                          "Falling back to local (mock) mode.")
            ErrorWindow(error_text)
            self.controller = None
            self.run_no_hardware()

    def _connect_local(self):
        """Open the in-process backend (real DAQ if present, else mock)."""
        try:
            back_settings = BackSettings(os.path.abspath(SETTINGS_FILE_REL_PATH))
            self.controller = LocalDeviceController(
                back_settings,
                calibration_path=self.settings.calib_path,
            )
            self.controller.connect()
            self._after_connect()
            self.start_live_stream()
        except Exception as exc:
            ErrorWindow(self._local_connect_error_text(exc))
            logger.exception("Local backend failed to start")
            self.controller = None
            self.sysStatusLabel.setText("Connection failed")

    @staticmethod
    def _local_connect_error_text(exc: Exception) -> str:
        """Map a connect failure to an actionable message for the operator.

        Message-mapping only -- the underlying exceptions are raised by the
        backend (``daq_device.py`` / ``ai_device.py``); we just translate the
        common real-hardware failure modes into something the operator can act
        on instead of the raw text.
        """
        msg = str(exc)
        if isinstance(exc, RuntimeError) and "No DAQ devices found" in msg:
            return ("No DAQ device found on the configured interface.\n"
                    "Check the USB cable / power and that the board enumerates "
                    "(MCC USB-2637), then press ON again.")
        if isinstance(exc, RuntimeError) and "SINGLE_ENDED" in msg:
            return ("The connected board reports no SINGLE_ENDED channels.\n"
                    "PIONER expects an MCC USB-2637; verify the hardware model "
                    "and the AI input-mode / range configuration.")
        if isinstance(exc, OSError):
            return ("Failed to load the uldaq driver library (libuldaq).\n"
                    "Install libuldaq and reinstall with the [hardware] extra, "
                    f"or run with the mock backend.\n\nDetails: {msg}")
        return f"Local backend failed to start:\n{msg}"

    def _after_connect(self):
        """Shared post-connect setup for both backends."""
        if self.settings.calib_path == DEFAULT_CALIBRATION_FILE_REL_PATH:
            self.apply_default_calib()
        else:
            self.apply_calib()
        for item in (self.experimentBox, self.controlTab):
            item.setEnabled(True)
        if self.controller is not None:
            # Idle monitor runs at the default rate; show the selected mode's
            # configured rate in the field and treat the loaded config as
            # confirmed (P1-31 Apply gate).
            self.controller.set_sample_rate(self.settings.sample_rate)
            self.scanSampleRateInput.setText(str(self.controller.rate_for_mode(self._selected_mode())))
            self._set_rate_confirmed(True)
            # Surface real-vs-mock so the operator is never guessing which
            # backend actually bound (the "run without hardware" checkbox only
            # picks Local vs Tango). backend_description is defined on every
            # DeviceController; getattr keeps this safe if that ever changes.
            desc = getattr(self.controller, "backend_description",
                           type(self.controller).__name__)
            self.sysStatusLabel.setText(f"Connected: {desc}")
            logger.info("Connected backend: %s", desc)

    def disconnect(self):
        self.stop_live_stream()
        self._cancel_iso_timer()
        # Abort an in-flight run before tearing down the controller, so the
        # worker stops cleanly (heater zeroed, partial finalised) rather than
        # erroring on a half-disconnected backend (P1-17 step 7b).
        if self._run_thread is not None and self.controller is not None:
            self.controller.stop_run()
            self._run_thread.join(timeout=3.0)
            self._run_thread = None
            self._run_worker = None
            self._set_running(False)
        self._heater_driven = False
        if self.controller is not None:
            self.controller.disconnect()
            self.controller = None
        [item.setEnabled(False) for item in [self.experimentBox, self.controlTab]]
        self.sysNoHardware.setEnabled(True)
        self.sysStatusLabel.setText("Not connected")
    
    def select_data_path(self):
        dpath = qt.QFileDialog.getExistingDirectory(self, "Choose folder to save experiment files", \
                                                    None, qt.QFileDialog.ShowDirsOnly)
        if dpath:
            dpath += '/'
            # Prefer relative-to-cwd so settings.json stays portable across
            # checkouts; fall back to absolute when the choice is outside cwd.
            self.settings.data_path = _relative_if_under_cwd(dpath)
            self.sysDataPathInput.setText(self.settings.data_path)
        self.sysDataPathInput.setCursorPosition(0)

    def show_help(self):
        self.configWindow = configWindow(parent=self)
        self.configWindow.show()

    def run_no_hardware(self):
        # Fallback when the Tango path is unavailable: switch to the
        # in-process LocalDeviceController (mock when no DAQ is attached),
        # so experiments and live streaming still work.
        self.sysNoHardware.setChecked(True)
        self.controlTabsWidget.setCurrentIndex(0)
        self.mainTabWidget.setCurrentIndex(0)
        if self.controller is None:
            self._connect_local()
    # ===================================
    # Calibration   

    def select_calibration_file(self):
        fname = qt.QFileDialog.getOpenFileName(self, "Choose calibration file", None, "*.json")[0]
        if fname:
            self.settings.calib_path = _relative_if_under_cwd(fname)
            self.calibPathInput.setText(self.settings.calib_path)
        self.calibPathInput.setCursorPosition(0)

    def apply_calib(self):
        if self.controller is None:
            return
        fpath = self.calibPathInput.text()
        if os.path.exists(os.path.abspath(fpath)):
            with open(self.calibPathInput.text(), 'r') as f:
                raw_calib = json.load(f)
                str_calib = json.dumps(raw_calib)
                self.controller.load_calibration(str_calib)
                self.controller.apply_calibration()
                self.get_calib_from_device()

    def apply_default_calib(self):
        if self.controller is None:
            return
        self.controller.apply_default_calibration()
        self.get_calib_from_device()
        self.calibPathInput.setText(os.path.abspath(DEFAULT_CALIBRATION_FILE_REL_PATH))
        self.calibPathInput.setCursorPosition(0)

    def get_calib_from_device(self):
        if self.controller is None:
            return
        calib_dict = self.controller.get_calibration()
        self.calibration = Dict2Class(calib_dict)

    def view_calibraton_info(self):
        self.calibWindow = calibWindow(parent=self)
        self.calibWindow.show()
    
    # ===================================
    # Settings
    def preload_settings(self):
        if not os.path.exists(SETTINGS_FOLDER_REL_PATH):
            os.makedirs(SETTINGS_FOLDER_REL_PATH)
        if not os.path.exists(SETTINGS_FILE_REL_PATH):
            shutil.copy(DEFAULT_SETTINGS_FILE_REL_PATH, SETTINGS_FILE_REL_PATH)
        if not os.path.exists(DATA_FOLDER_REL_PATH):
            os.makedirs(DATA_FOLDER_REL_PATH)

        self.load_settings_from_file()
        if not getattr(self, "settings", None):
            raise SystemExit("Failed to load settings; cannot start UI.")

        if not os.path.exists(self.settings.data_path):
            error_text = "Incorrect data path specified.\nIt will be set to {}".format(DATA_FOLDER_REL_PATH)
            ErrorWindow(error_text)
            self.settings.data_path = _relative_if_under_cwd(DATA_FOLDER_REL_PATH)
        self.sysDataPathInput.setText(self.settings.data_path)
        self.sysDataPathInput.setCursorPosition(0)

        if not os.path.exists(self.settings.calib_path):
            error_text = "Incorrect calibration file specified.\nIt will be set to default calibration."
            ErrorWindow(error_text)
            self.settings.calib_path = _relative_if_under_cwd(DEFAULT_CALIBRATION_FILE_REL_PATH)
        self.calibPathInput.setText(self.settings.calib_path)
        self.calibPathInput.setCursorPosition(0)

        self.scanSampleRateInput.setText(str(self.settings.sample_rate))

        self.freqInput.setText(str(self.settings.modulation_frequency))
        self.amplitudeInput.setText(str(self.settings.modulation_amplitude))
        self.offsetInput.setText(str(self.settings.modulation_offset))  

    def apply_sample_rate(self):
        if self.controller is None:
            return
        try:
            rate = int(self.scanSampleRateInput.text())
        except ValueError:
            ErrorWindow("Sample rate must be an integer (Hz).")
            return
        # Session override of the selected mode's rate; AO == AI is kept by the
        # controller, which rejects odd / sub-Nyquist rates. Only confirm the
        # Apply gate (enabling arm/set) once the rate is accepted.
        try:
            self.controller.override_mode_rate(self._selected_mode(), rate)
        except ValueError as exc:
            ErrorWindow(f"Invalid sample rate:\n{exc}")
            return
        self._set_rate_confirmed(True)

    def reset_sample_rate(self):
        if self.controller is None:
            return
        self.controller.reset_sample_rate()
        self.scanSampleRateInput.setText(str(self.controller.rate_for_mode(self._selected_mode())))
        self._set_rate_confirmed(True)

    def get_sample_rate_from_device(self):
        if self.controller is None:
            return self.settings.sample_rate
        return self.controller.get_sample_rate()

    def apply_modulation_params(self):
        try:
            self.settings.modulation_frequency = float(self.freqInput.text())
            self.settings.modulation_amplitude = float(self.amplitudeInput.text())
            self.settings.modulation_offset = float(self.offsetInput.text())
        except ValueError:
            ErrorWindow("Modulation inputs must be numeric.")

    def reset_modulation_params(self):
        self.freqInput.setText(str(self.settings.modulation_frequency))
        self.amplitudeInput.setText(str(self.settings.modulation_amplitude))
        self.offsetInput.setText(str(self.settings.modulation_offset))


    # ===================================
    # Mode selection (fast / slow / iso)
    # ===================================
    #: Ramp-editor widgets shared by fast and slow modes.
    _RAMP_WIDGET_NAMES = (
        "experimentTimeComboBox", "experimentTempComboBox", "experimentTable",
        "loadTxtButton", "armButton", "stopButton", "startButton",
        "holdFinalValue",
    )
    #: Set/Off widgets used by iso mode only.
    _ISO_WIDGET_NAMES = (
        "isoLabel", "setComboBox", "setInput", "setInputUnits",
        "unsetTempVoltButton", "setTempVoltButton",
    )

    def _selected_mode(self) -> str:
        """Backend mode name for the current combo selection."""
        return self.modeComboBox.currentText().strip().lower()

    def _on_mode_changed(self):
        """Show the ramp editor for fast/slow, the Set/Off block for iso.

        Fast and slow are identical from the GUI's side -- both drive the
        ramp table; the only difference is the mode name sent on arm/run
        (slow adds AC modulation in the backend). Iso is a static
        set-and-hold, so it uses its own controls.
        """
        is_iso = self._selected_mode() == "iso"
        for name in self._RAMP_WIDGET_NAMES:
            getattr(self, name).setVisible(not is_iso)
        for name in self._ISO_WIDGET_NAMES:
            getattr(self, name).setVisible(is_iso)
        # Switching modes changes the configured sample rate (P1-31). Show the
        # new mode's rate and require an explicit Apply before arming/setting.
        if self.controller is not None:
            self.scanSampleRateInput.setText(str(self.controller.rate_for_mode(self._selected_mode())))
            self._set_rate_confirmed(False)

    def _set_rate_confirmed(self, confirmed: bool) -> None:
        """Gate the experiment-launch buttons on the Apply state (P1-31)."""
        self._rate_confirmed = confirmed
        self.armButton.setEnabled(confirmed)
        self.setTempVoltButton.setEnabled(confirmed)

    # ===================================
    # Fast / slow heating (ramp editor)

    def fh_arm(self):
        xOption = 1000 if self.experimentTimeComboBox.currentIndex()==1 else 1    # 0 - time in ms, 1 - time in s
        # 0 - temp (°C), 1 - volt (V). Heater channel key depends on this.
        is_voltage_program = self.experimentTempComboBox.currentIndex() == 1
        heater_value_key = "volt" if is_voltage_program else "temp"
        uncorrectedProfile = np.array([[],[]], dtype=float)
        for i in range(self.experimentTable.rowCount()):
            # Cells are populated with QTableWidgetItem('0') in mainWindowUi
            # __init__, so item(i, c) is never None here.
            t_item = self.experimentTable.item(i, 0)
            v_item = self.experimentTable.item(i, 1)
            assert t_item is not None and v_item is not None
            uncorrectedProfile = np.hstack((uncorrectedProfile,
                                            [[float(t_item.text())],
                                            [float(v_item.text())]]))
        # Trim trailing zero-padded rows: keep up to the row with max time.
        # If every cell is zero the resulting profile would have duration 0,
        # which the backend (rightly) rejects -- fail loudly here instead of
        # sending a degenerate program over Tango.
        if not np.any(uncorrectedProfile[0] > 0):
            ErrorWindow("Program table is empty: enter at least one row with time > 0.")
            return
        correctedProfile = uncorrectedProfile[:, :(np.argmax(uncorrectedProfile[0])+1)]
        correctedProfile = np.insert(correctedProfile, 0, 0, axis=1)
        self.time_table = xOption*correctedProfile[0] # changing s to ms if needed
        self.temp_table = correctedProfile[1]
        
        self.progressBar.setValue(0)  
        self.controlTabsWidget.setCurrentIndex(1) 
        self.progPlot.resultPlot.clear()
        
        y_label = self.experimentTempComboBox.currentText()
        x_label = self.experimentTimeComboBox.currentText()
        self.progPlot.resultPlot.addCurve(x=self.time_table, y=self.temp_table, 
                                            legend="temperature", 
                                            color=self.progPlot.curveColors['red'])
        self.progPlot.resultPlot.getXAxis().setLabel(x_label)
        self.progPlot.resultPlot.getYAxis().setLabel(y_label)

        # generating time_temp_volt_tables as dict, converting it to str
        # to pass to controller.arm_fast_heat
        self.time_temp_volt_tables = {'ch0':{}, 'ch1':{}, 'ch2':{}}

        # 0.1V on 0 channel
        self.time_temp_volt_tables['ch0']['time'] = self.time_table.tolist()
        self.time_temp_volt_tables['ch0']['volt'] = [0.1]*len(self.time_table) 

        # Signal to heater - channel 1 (use the unit selected by the user;
        # silently sending ``temp`` while the user picked ``Voltage`` would
        # send the value through the calibration polynomial, which is wrong).
        self.time_temp_volt_tables['ch1']['time'] = self.time_table.tolist()
        self.time_temp_volt_tables['ch1'][heater_value_key] = self.temp_table.tolist()

        # 2.5V trigger signal like gate form
        self.time_temp_volt_tables['ch2']['time'] =  self.time_table.tolist()
        self.time_temp_volt_tables['ch2']['time'].insert(-1, self.time_temp_volt_tables['ch2']['time'][-1]-1)
        self.time_temp_volt_tables['ch2']['volt'] = [2.5]*(len(self.time_table)+1)
        self.time_temp_volt_tables['ch2']['volt'][-1] = 0

        self.time_temp_volt_tables_str = json.dumps(self.time_temp_volt_tables)
        if self.controller is None:
            return  # no backend: program plotted, but cannot be armed
        if not self._rate_confirmed:
            ErrorWindow("Press Apply to confirm the sample rate before arming.")
            return
        # Fast and slow share this ramp program; the backend mode name picks
        # whether AC modulation is layered on (slow) or not (fast).
        self.controller.arm(self._selected_mode(), self.time_temp_volt_tables_str)

    def _fh_plot_df(self, df):
        """Plot the result DataFrame returned by ``controller.run_*``."""
        self.resultsDataWidget.clear()
        if df is not None and not df.empty:
            _keys = list(df.keys())
            if 'time' in _keys:
                _keys.remove('time')
            for idx, key in enumerate(_keys):
                color = self.resultsDataWidget.curveColors[list(self.resultsDataWidget.curveColors.keys())[idx % len(self.resultsDataWidget.curveColors)]]
                self.resultsDataWidget.addCurve(df['time'],
                                                df[key],
                                                legend=key,
                                                color=color)
            for curve in self.resultsDataWidget.resultPlot.getItems():
                if curve.getName() != "temp":
                    curve.setVisible(False)
            self.mainTabWidget.setCurrentIndex(1)
        self.resultsDataWidget.resultPlot.resetZoom()

    #: Max points plotted in the result view; the on-disk record can be far
    #: larger, so we read it back decimated (P1-17 step 4c-3).
    _RESULT_PLOT_MAX_POINTS = 5000

    def fh_run(self):
        if self.controller is None:
            ErrorWindow("No backend connection: cannot run experiment.")
            return
        self._start_run_worker()

    def _start_run_worker(self) -> bool:
        """Launch ``controller.run()`` on a worker thread (P1-17 step 7).

        ``run()`` can block for the whole experiment (slow / finite-iso last
        minutes to hours), so doing it inline would freeze the GUI and make Stop
        impossible. The worker writes the full record to disk and emits the
        RunResult; we plot it (decimated) on completion. Returns False if a run
        is already in flight or there is no backend.
        """
        if self.controller is None or self._run_thread is not None:
            return False
        self._set_running(True)
        worker = _RunWorker(self.controller)
        worker.finished.connect(self._on_run_finished)
        self._run_worker = worker  # keep a reference so it is not GC'd
        self._run_thread = threading.Thread(target=worker.run, daemon=True)
        self._run_thread.start()
        return True

    def _on_run_finished(self, result):
        """Main-thread slot: plot the finished run (decimated from disk)."""
        self._run_thread = None
        self._run_worker = None
        self._heater_driven = False  # the run finished -> heater no longer driven
        self._set_running(False)
        if result is None or result.rows == 0:
            # No data (e.g. an aborted run wrote nothing); clear the result plot
            # rather than read a file that was never written.
            self._fh_plot_df(pd.DataFrame())
            return
        data = read_calibrated_h5(result.cal_path, max_points=self._RESULT_PLOT_MAX_POINTS)
        self._fh_plot_df(pd.DataFrame(data))

    def fh_stop(self):
        """Abort an in-flight run (zeroes the heater + finalises a partial)."""
        if self.controller is not None:
            self.controller.stop_run()

    def _set_running(self, running: bool) -> None:
        """Toggle button state for the duration of a run (P1-17 step 7).

        Disables every experiment-launch control (fast/slow arm+start, iso Set)
        and the mode combo; enables Stop. The iso Off button stays enabled -- it
        is the abort for a finite iso run.
        """
        self.startButton.setEnabled(not running)
        self.armButton.setEnabled(not running and self._rate_confirmed)
        self.stopButton.setEnabled(running)
        self.setTempVoltButton.setEnabled(not running and self._rate_confirmed)
        self.modeComboBox.setEnabled(not running)

    # ===================================
    # Iso (set) mode
    # The "Set" / "Off" pair must target the *same* AO channel so that "Off"
    # actually neutralises the previous "Set". The heater is wired on ch1 in
    # ``fh_arm`` above (and is the default ``modulation_channel`` in the
    # backend), so both endpoints write to ch1.
    HEATER_CHANNEL_KEY = HEATER_AO

    def set_temp_volt(self):
        if self.controller is None:
            ErrorWindow("No backend connection: cannot set iso value.")
            return
        if not self._rate_confirmed:
            ErrorWindow("Press Apply to confirm the sample rate before setting iso.")
            return
        try:
            value = float(self.setInput.text())
        except ValueError:
            ErrorWindow("Iso input must be numeric.")
            return
        # Optional hold duration (seconds). Empty -> eternal hold until Off;
        # a positive value runs a timed iso program that auto-returns to 0 V.
        duration = 0.0
        dtext = self.setDurationInput.text().strip()
        if dtext:
            try:
                duration = float(dtext)
            except ValueError:
                ErrorWindow("Iso duration must be numeric seconds, or empty for eternal hold.")
                return
        key = "temp" if self.setComboBox.currentText() == "Temperature" else "volt"
        if duration > 0:
            # Finite iso experiment: arm a constant program of duration D and run
            # it on the worker thread -- this RECORDS (raw U + calibrated T) and
            # auto-stops after D (P1-17 step 5/7). Off acts as the abort.
            program = {self.HEATER_CHANNEL_KEY: {
                "time": [0, int(round(duration * 1000))], key: [value, value]}}
            self.controller.arm_iso_mode(json.dumps(program))
            self._heater_driven = True
            if not self._start_run_worker():
                self._heater_driven = False  # a run was already in flight
        else:
            # Eternal hold (no recording): drive AO and hold until Off. The
            # persistent AI stream keeps the live plot alive (P1-5); the heater
            # is genuinely driven, so the live Thtr readout is meaningful.
            chan_temp_volt = {self.HEATER_CHANNEL_KEY: {key: value}}
            self.chan_temp_volt_str = json.dumps(chan_temp_volt)
            self.controller.arm_iso_mode(self.chan_temp_volt_str)
            self.controller.start_iso_hold()
            self._heater_driven = True

    def unset_temp_volt(self):
        if self.controller is None:
            return
        # "Off": if a finite iso run is in flight it acts as Stop (abort ->
        # zero + finalise partial). Otherwise it ends an eternal hold by actively
        # driving 0 V (a bare AO stop would latch the last setpoint hot).
        if self._run_thread is not None:
            self.controller.stop_run()
            return
        self._cancel_iso_timer()
        chan_temp_volt = {self.HEATER_CHANNEL_KEY: {"volt": 0}}
        self.chan_temp_volt_str = json.dumps(chan_temp_volt)
        self.controller.arm_iso_mode(self.chan_temp_volt_str)
        self.controller.start_iso_hold()
        self._heater_driven = False

    def _cancel_iso_timer(self):
        if self._iso_timer is not None:
            self._iso_timer.stop()
            self._iso_timer = None



    # ===================================
    def save_settings_to_file(self, fpath=False):
        # function is used to save settings to default file or to special file if specified
        if not fpath:
            fpath = os.path.abspath(SETTINGS_FILE_REL_PATH)
        else:
            fpath = qt.QFileDialog.getSaveFileName(self, "Select file and path to save settings:", None, "*.json")[0]
        if fpath:
            with open(fpath, 'r') as f:
                file_settings = json.load(f)

            file_settings[SERVER_SETTINGS_FIELD] = self.settings.get_server_settings()
            file_settings[EXPERIMENT_SETTINGS_FIELD] = self.settings.get_exp_settings()

            with open(fpath, 'w') as f:
                json.dump(file_settings, f, separators=(',', ': '), indent=4)

    def load_settings_from_file(self, fpath=False):
        # function is used to load default settings or to load special config from file if specified
        if not fpath:
            fpath = os.path.abspath(SETTINGS_FILE_REL_PATH)
        else:
            fpath = qt.QFileDialog.getOpenFileName(self, "Choose file with settings:", None, "*.json")[0]
        try:
            self.settings = FrontSettings(fpath)
            self.disconnect()
        except Exception:
            error_text = "Settings file is missing or corrupted! Settings will be reset to default."
            ErrorWindow(error_text)
            self.reset_settings()

    def reset_settings(self):
        # reset config params; used default attributes from Params class
        self.settings = FrontSettings(DEFAULT_SETTINGS_FILE_REL_PATH)

    def closeEvent(self, event):
        # dumping current settings to ./settings/settings.json and closing all the windows
        self.save_settings_to_file()
        for window in qt.QApplication.topLevelWidgets():
            window.close()




