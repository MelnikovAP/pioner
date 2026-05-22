import json
import os
from pioner_app.paths import PROJECT_ROOT
from silx.gui import qt

from pioner_app.ui.mainWindowUi import mainWindowUi
from pioner_app.ui.h_windows import ErrorWindow, calibWindow
from pioner_app.core.calibration import Calibration
from pioner_app.hardware.daq_controller import get_daq_controller
from pioner_app.core.basemath import DataProcessor
import numpy as np
from pioner_app.core.settings import settings
from pioner_app.ui.localization import apply_language, tr
from pioner_app.ui.calibration_wizard import CalibrationWizard


BASE_DIR = PROJECT_ROOT


def _dialog_options():
    """???????? ?????? `dialog_options`."""
    options = qt.QFileDialog.Options()
    options |= qt.QFileDialog.DontUseNativeDialog
    return options


def _center_on_parent(widget, parent):
    """???????? ?????? `center_on_parent`."""
    if parent is None:
        return
    widget.adjustSize()
    parent_rect = parent.frameGeometry()
    center = parent_rect.center()
    frame = widget.frameGeometry()
    frame.moveCenter(center)
    widget.move(frame.topLeft())


class mainWindow(mainWindowUi):
    def __init__(self, parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super(mainWindow, self).__init__(parent)

        self.ctrl = get_daq_controller()
        self.settings = settings
        self.currentExpFilePath = None
        self.direct_daq_control = None
        self.samplerate = None
        self.device = None
        self.calibration = Calibration()
        self.calibration.read(str(BASE_DIR / "default_calibration.json"))
        self.values_processor = DataProcessor(calibration=self.calibration, sample_rate=settings.sample_rate)
        self._temperature_error_offset = 0.0
        self._phase_offset = 0.0
        self._latest_values_metrics = None

        self.sysOnButton.clicked.connect(self.sysOnButtonPressed)
        self.sysOffButton.clicked.connect(self.disconnect)
        self.sysSetupButton.clicked.connect(self.open_config_window)
        self.calibPathButton.clicked.connect(self.select_calibration_file)
        self.calibViewButton.clicked.connect(self.open_calibration_window)
        self.calibApplyButton.clicked.connect(self.apply_calibration)
        self.applyScanSampleRateButton.clicked.connect(self.apply_sample_rate)
        self.applyModulationParamsButton.clicked.connect(self.apply_modulation_params)
        self.resetModulationParamsButton.clicked.connect(self.stop_modulation)

        self.exp_widget.result_ready.connect(self.on_experiment_finished)
        self.ctrl.progress_changed.connect(self.update_progress)
        self.ctrl.input_gains_changed.connect(self.on_controller_input_gains_changed)

        self._values_timer = qt.QTimer(self)
        self._values_timer.timeout.connect(self.update_values_widget)
        self._values_timer.start(250)
        if hasattr(self, "valueswind"):
            self.valueswind.terror0Button.clicked.connect(self.zero_temperature_error)
            self.valueswind.tresetButton.clicked.connect(self.reset_temperature_error)
            self.valueswind.phase0Button.clicked.connect(self.zero_phase_offset)
            self.valueswind.phaseResetButton.clicked.connect(self.reset_phase_offset)

        if hasattr(self, "inputGainsPanel"):
            self.inputGainsPanel.stateChanged.connect(self.on_input_gains_panel_changed)

        if getattr(settings, "connection_mode", "direct") == "tango":
            self.tangocheck.setChecked(True)
        else:
            self.dirconn.setChecked(True)

        self.load_ui_from_settings()
        self.update_hardware_status()
        apply_language(self, getattr(settings, "ui_language", "en"))

    def load_ui_from_settings(self):
        """????????? ?????? `load_ui_from_settings`."""
        self.scanSampleRateInput.setText(str(settings.sample_rate))
        self.freqInput.setText(str(settings.mod_freq))
        self.amplitudeInput.setText(str(settings.mod_amp))
        self.offsetInput.setText(str(settings.mod_offset))
        results_path = settings.data_path or str(BASE_DIR / "results")
        self.sysDataPathInput.setText(results_path)
        settings.data_path = results_path
        self.calibPathInput.setText(settings.calibration_path or "")
        if hasattr(self, "inputGainsPanel"):
            self.inputGainsPanel.set_state(
                ranges=getattr(settings, "input_gain_ranges", {}),
                auto_gain=getattr(settings, "input_gain_auto", {}),
            )

        calib_path = settings.calibration_path
        if calib_path and os.path.exists(calib_path):
            try:
                calib = Calibration()
                calib.read(calib_path)
                self.set_active_calibration(calib, path=calib_path)
            except Exception as exc:
                print(f"Calibration preload failed: {exc}")

    def sysOnButtonPressed(self):
        """???????? ?????? `sysOnButtonPressed`."""
        try:
            mode = "tango" if self.tangocheck.isChecked() else "direct"
            self.ctrl.set_connection_mode(mode)
            settings.connection_mode = mode
            self.ctrl.connect()
            self.ctrl.reset_ao_outputs()
            self.on_controller_input_gains_changed(
                dict(getattr(settings, "input_gain_ranges", {})),
                dict(getattr(settings, "input_gain_auto", {})),
            )
            print("DAQ connected")
            self.update_hardware_status()
            self.experimentBox.setEnabled(True)
            self.mainTabWidget.setEnabled(True)
            if hasattr(self, "mainTabWidget") and hasattr(self, "signalsTab"):
                self.mainTabWidget.setCurrentWidget(self.signalsTab)
            if hasattr(self, "signalsWidget"):
                self.signalsWidget.start_acquisition()
        except Exception as exc:
            error_text = f"DAQ connection error: {exc}"
            print(error_text)
            ErrorWindow(error_text)

    def on_input_gains_panel_changed(self, ranges, auto_gain):
        """???????????? ??????? `on_input_gains_panel_changed`."""
        settings.input_gain_ranges = dict(ranges)
        settings.input_gain_auto = dict(auto_gain)
        try:
            self.ctrl.apply_input_gains(ranges, auto_gain, restart=True, emit_signal=False)
        except Exception as exc:
            ErrorWindow(f"Input gains error: {exc}")

    def on_controller_input_gains_changed(self, ranges, auto_gain):
        """???????????? ??????? `on_controller_input_gains_changed`."""
        settings.input_gain_ranges = dict(ranges)
        settings.input_gain_auto = dict(auto_gain)
        if hasattr(self, "inputGainsPanel"):
            self.inputGainsPanel.set_state(ranges=ranges, auto_gain=auto_gain)

    def disconnect(self):
        """????????? ?????? `disconnect`."""
        try:
            self.ctrl.disconnect()
            print("DAQ disconnected")
            self.update_hardware_status()
        except Exception as exc:
            print(f"Disconnect error: {exc}")

        self.clear_values_widget()
        self.experimentBox.setEnabled(False)
        self.mainTabWidget.setEnabled(False)

    def update_hardware_status(self):
        """????????? ?????? `update_hardware_status`."""
        ctrl = get_daq_controller()
        if not ctrl.device:
            self.hardware_label.setText(tr("None"))
            self.hardware_label.setStyleSheet("color: gray;")
            self.status_label.setText(tr("DISCONNECTED"))
            self.status_label.setStyleSheet("color: white; background-color: #d9534f; padding: 2px; border-radius: 3px; font-weight: bold;")
            return

        name = getattr(ctrl, "device_name", "DAQ") or "DAQ"
        self.hardware_label.setText(name)
        self.hardware_label.setStyleSheet("color: #00aa00; font-weight: bold;")
        self.status_label.setText(tr("CONNECTED"))
        self.status_label.setStyleSheet("color: white; background-color: #5cb85c; padding: 2px; border-radius: 3px; font-weight: bold;")

    def set_running_status(self):
        """????????????? ?????? `set_running_status`."""
        self.status_label.setText(tr("RUNNING"))
        self.status_label.setStyleSheet("color: black; background-color: #f0ad4e; padding: 2px; border-radius: 3px; font-weight: bold;")
        apply_language(self, getattr(settings, "ui_language", "en"))

    def apply_modulation_params(self):
        """????????? ?????? `apply_modulation_params`."""
        amp = float(self.amplitudeInput.text())
        freq = float(self.freqInput.text())
        offs = float(self.offsetInput.text())
        settings.mod_freq = freq
        settings.mod_amp = amp
        settings.mod_offset = offs
        self.start_modulation(freq, amp, offs)

    def start_modulation(self, freq, amp, offs):
        """????????? ?????? `start_modulation`."""
        try:
            self.ctrl.start_modulation(freq, amp, offs)
            print("Modulation started")
        except Exception as exc:
            ErrorWindow(f"Modulation error: {exc}")

    def stop_modulation(self):
        """????????????? ?????? `stop_modulation`."""
        try:
            self.ctrl.stop_modulation()
            print("Modulation stopped")
        except Exception as exc:
            ErrorWindow(f"Stop error: {exc}")

    def apply_sample_rate(self):
        """????????? ?????? `apply_sample_rate`."""
        rate = int(self.scanSampleRateInput.text())
        settings.sample_rate = rate
        self.scanSampleRateInput.setText(str(rate))
        self.ctrl.set_sample_rate(rate)

    def on_experiment_finished(self, data):
        """???????????? ??????? `on_experiment_finished`."""
        if data is None:
            return

        processor = DataProcessor(calibration=self.ctrl.calibration)
        ref = self.ctrl.em.get_ref_signal(channel=1) if self.ctrl.em else None
        result = processor.process_fast_heat(data, calibration=self.calibration, ref_signal=ref)
        result_folder = self.sysDataPathInput.text().strip() or str(BASE_DIR / "results")
        settings.data_path = result_folder
        processor.save(
            result,
            folder=result_folder,
            fmt="hdf5",
            calibration=self.calibration,
            settings_obj=settings.build_runtime_config(
                connection_mode="tango" if self.tangocheck.isChecked() else "direct",
                tango_host=getattr(settings, "tango_host", ""),
                device_proxy=getattr(settings, "device_proxy", ""),
                http_host=getattr(settings, "http_host", ""),
                calibration_path=self.calibPathInput.text().strip(),
                data_path=result_folder,
                sample_rate=int(self.scanSampleRateInput.text()),
                mod_freq=float(self.freqInput.text()),
                mod_amp=float(self.amplitudeInput.text()),
                mod_offset=float(self.offsetInput.text()),
                input_gain_ranges=self.inputGainsPanel.get_state()["ranges"] if hasattr(self, "inputGainsPanel") else {},
                input_gain_auto=self.inputGainsPanel.get_state()["auto_gain"] if hasattr(self, "inputGainsPanel") else {},
            ),
        )
        self.resultsDataWidget.set_processed_data(
            result,
            profile_segments=list(getattr(self.exp_widget, "segments", [])),
            sample_rate=settings.sample_rate,
        )
        self.mainTabWidget.setCurrentWidget(self.resultTab)

    def update_progress(self, value):
        """????????? ?????? `update_progress`."""
        self.progressBar.setValue(value)

    def update_fake_progress(self):
        """????????? ?????? `update_fake_progress`."""
        if self._progress_value < 95:
            self._progress_value += 1
            self.progressBar.setValue(self._progress_value)

    def apply_calibration(self):
        """????????? ?????? `apply_calibration`."""
        path = self.calibPathInput.text().strip()
        if not path:
            return
        try:
            calib = Calibration()
            calib.read(path)
            self.set_active_calibration(calib, path=path)
        except Exception as exc:
            ErrorWindow(f"Calibration error: {exc}")

    def set_active_calibration(self, calib, path=None):
        """????????????? ?????? `set_active_calibration`."""
        self.calibration = calib
        self.values_processor.calibration = calib
        self.ctrl.calibration = calib
        if self.ctrl.em:
            self.ctrl.em.calibration = calib
        if path:
            abs_path = os.path.abspath(path)
            self.calibPathInput.setText(abs_path)
            settings.calibration_path = abs_path
        if hasattr(self, "calib_window"):
            self.calib_window.update_calib_input_fields()

    def _wrap_phase(self, value):
        """???????? ?????? `wrap_phase`."""
        while value > 180.0:
            value -= 360.0
        while value < -180.0:
            value += 360.0
        return value

    def _current_lockin_frequency(self):
        """???????? ?????? `current_lockin_frequency`."""
        try:
            return float(self.freqInput.text())
        except Exception:
            return 0.0

    def _current_demod_periods(self):
        """???????? ?????? `current_demod_periods`."""
        try:
            if hasattr(self, "modulationWidget") and hasattr(self.modulationWidget, "periods_box"):
                return max(3, int(self.modulationWidget.periods_box.value()))
        except Exception:
            pass
        return 5

    def _values_interval_ms(self):
        """???????? ?????? `values_interval_ms`."""
        return 1000 if self.ctrl.is_fast_heat_running() else 250

    def _values_points_per_read(self):
        """???????? ?????? `values_points_per_read`."""
        freq = max(self._current_lockin_frequency(), 0.1)
        periods = max(self._current_demod_periods(), 3)
        samples_per_period = max(1, int(round(settings.sample_rate / freq)))
        target = samples_per_period * (periods + 2)
        target = max(target, 2000)
        target = min(target, 8000)
        return int(target)

    def _set_values_timer_interval(self):
        """????????????? ?????? `set_values_timer_interval`."""
        interval = self._values_interval_ms()
        if self._values_timer.interval() != interval:
            self._values_timer.setInterval(interval)

    def _ensure_values_acquisition(self):
        """???????? ?????? `ensure_values_acquisition`."""
        if not self.ctrl.em or self.ctrl.is_fast_heat_running() or getattr(self.ctrl, "_running", False):
            return
        if self.ctrl.is_acquisition_running():
            return
        try:
            points = self._values_points_per_read()
            self.ctrl.start_acquisition(owner="values", points_per_channel=points)
        except Exception:
            pass

    def _format_value(self, value, suffix="", precision=3):
        """???????? ?????? `format_value`."""
        if value is None:
            return " ---"
        try:
            number = float(value)
        except Exception:
            return " ---"
        if not np.isfinite(number):
            return " ---"
        return f" {number:.{precision}f}{suffix}"

    def clear_values_widget(self):
        """??????? ?????? `clear_values_widget`."""
        if not hasattr(self, "valueswind"):
            return
        for attr in (
            "rhtrabsValueLabel",
            "rhtrdynValueLabel",
            "umodhtrValueLabel",
            "ihtrValueLabel",
            "tauxValueLabel",
            "ttplValueLabel",
            "thtrValueLabel",
            "thtrdynValueLabel",
            "terrorValueLabel",
            "frequencyValueLabel",
            "amplitudeValueLabel",
            "offsetValueLabel",
            "powerValueLabel",
            "phaseValueLabel",
        ):
            getattr(self.valueswind, attr).setText(" ---")
        self._latest_values_metrics = None
        if hasattr(self, 'calib_window'):
            self.calib_window.update_live_measurements(None)

    def _build_values_metrics(self, data):
        """???????? ?????? `build_values_metrics`."""
        if data is None:
            return None
        arr = np.asarray(data, dtype=float)
        if arr.ndim != 2 or arr.shape[0] < 8 or arr.shape[1] < 6:
            return None
        self.values_processor.sample_rate = settings.sample_rate
        metrics = self.values_processor.analyze_slow_heating_chunk(
            arr,
            frequency=self._current_lockin_frequency(),
            method="lockin",
            periods=self._current_demod_periods(),
        )
        if not metrics:
            return None
        ihtr = float(metrics.get("Ihtr", 0.0))
        uhtr = float(metrics.get("Uhtr", 0.0))
        rhtr_abs = uhtr / ihtr if abs(ihtr) > 1e-9 else 0.0
        metrics["RhtrAbs"] = rhtr_abs
        metrics["Terror"] = float(metrics.get("Thtr", 0.0) - metrics.get("Ttpl", 0.0) - self._temperature_error_offset)
        metrics["PhaseAdjusted"] = self._wrap_phase(float(metrics.get("phase", 0.0)) - self._phase_offset)
        metrics["FreqDisplay"] = self._current_lockin_frequency()
        try:
            metrics["OffsetDisplay"] = float(self.offsetInput.text())
        except Exception:
            metrics["OffsetDisplay"] = 0.0
        return metrics

    def _render_values_metrics(self, metrics):
        """???????? ?????? `render_values_metrics`."""
        if not hasattr(self, "valueswind"):
            return
        vw = self.valueswind
        vw.rhtrabsValueLabel.setText(self._format_value(metrics.get("RhtrAbs"), precision=3))
        vw.rhtrdynValueLabel.setText(self._format_value(metrics.get("Rhtrd"), precision=3))
        vw.umodhtrValueLabel.setText(self._format_value(metrics.get("Uhtr"), precision=3))
        vw.ihtrValueLabel.setText(self._format_value(metrics.get("Ihtr"), precision=3))
        vw.tauxValueLabel.setText(self._format_value(metrics.get("Taux"), precision=2))
        vw.ttplValueLabel.setText(self._format_value(metrics.get("Ttpl"), precision=2))
        vw.thtrValueLabel.setText(self._format_value(metrics.get("Thtr"), precision=2))
        vw.thtrdynValueLabel.setText(self._format_value(metrics.get("Thtrd"), precision=2))
        vw.terrorValueLabel.setText(self._format_value(metrics.get("Terror"), precision=2))
        vw.frequencyValueLabel.setText(self._format_value(metrics.get("FreqDisplay"), precision=2))
        vw.amplitudeValueLabel.setText(self._format_value(metrics.get("amplitude"), precision=3))
        vw.offsetValueLabel.setText(self._format_value(metrics.get("OffsetDisplay"), precision=3))
        vw.powerValueLabel.setText(self._format_value(metrics.get("power"), precision=6))
        vw.phaseValueLabel.setText(self._format_value(metrics.get("PhaseAdjusted"), precision=2))

    def update_values_widget(self):
        """????????? ?????? `update_values_widget`."""
        self._set_values_timer_interval()
        if not self.ctrl.em:
            self.clear_values_widget()
            return
        self._ensure_values_acquisition()
        data = None
        if self.ctrl.is_acquisition_running():
            try:
                data = self.ctrl.peek_data(points=self._values_points_per_read())
            except Exception:
                data = self.ctrl.get_last_data()
        else:
            data = self.ctrl.get_last_data()
        metrics = self._build_values_metrics(data)
        if metrics is None:
            if self._latest_values_metrics is None:
                self.clear_values_widget()
            return
        self._latest_values_metrics = metrics
        self._render_values_metrics(metrics)
        if hasattr(self, 'calib_window'):
            self.calib_window.update_live_measurements(metrics)

    def zero_temperature_error(self):
        """???????? ?????? `zero_temperature_error`."""
        metrics = self._latest_values_metrics
        if not metrics:
            return
        self._temperature_error_offset += float(metrics.get("Terror", 0.0))
        self.update_values_widget()

    def reset_temperature_error(self):
        """?????????? ?????? `reset_temperature_error`."""
        self._temperature_error_offset = 0.0
        self.update_values_widget()

    def zero_phase_offset(self):
        """???????? ?????? `zero_phase_offset`."""
        metrics = self._latest_values_metrics
        if not metrics:
            return
        self._phase_offset = self._wrap_phase(float(metrics.get("phase", 0.0)))
        self.update_values_widget()

    def reset_phase_offset(self):
        """?????????? ?????? `reset_phase_offset`."""
        self._phase_offset = 0.0
        self.update_values_widget()

    def set_calibration(self, calib):
        """????????????? ?????? `set_calibration`."""
        self.set_active_calibration(calib)

    def apply_default_calib(self):
        """????????? ?????? `apply_default_calib`."""
        default_path = str(BASE_DIR / "default_calibration.json")
        self.calibPathInput.setText(default_path)
        self.apply_calibration()

    def open_calibration_window(self):
        """????????? ?????? `open_calibration_window`."""
        if not hasattr(self, "calib_window"):
            self.calib_window = calibWindow(self)
        self.calib_window.update_calib_input_fields()
        self.calib_window.update_live_measurements(self._latest_values_metrics)
        apply_language(self.calib_window, getattr(settings, "ui_language", "en"))
        self.calib_window.show()
        self.calib_window.raise_()
        self.calib_window.activateWindow()

    def start_calibration_wizard(self):
        """Starts the interactive calibration workflow from the calibration window."""
        wizard = CalibrationWizard(self)
        wizard.run()

    def select_calibration_file(self):
        """???????? ?????? `select_calibration_file`."""
        path, _ = qt.QFileDialog.getOpenFileName(
            self,
            "Select calibration file",
            self.calibPathInput.text() or str(BASE_DIR),
            "JSON files (*.json)",
            options=_dialog_options(),
        )
        if path:
            self.calibPathInput.setText(path)

    def apply_server_settings(self, tango_host=None, device_proxy=None, http_host=None):
        """????????? ?????? `apply_server_settings`."""
        if tango_host is not None:
            settings.tango_host = tango_host
        if device_proxy is not None:
            settings.device_proxy = device_proxy
        if http_host is not None:
            settings.http_host = http_host

    def open_config_window(self):
        """????????? ?????? `open_config_window`."""
        if not hasattr(self, "config_window"):
            from h_windows import configWindow
            self.config_window = configWindow(self)
        apply_language(self.config_window, getattr(settings, "ui_language", "en"))
        self.config_window.show()
        self.config_window.raise_()
        self.config_window.activateWindow()

    def load_settings_from_file(self, fpath=False):
        """????????? ?????? `load_settings_from_file`."""
        settings.reload()
        self.settings = settings
        self.load_ui_from_settings()
        if hasattr(self, "config_window"):
            self.config_window.tangoHostInput.setText(settings.tango_host)
            self.config_window.deviceProxyInput.setText(settings.device_proxy)
            self.config_window.httpHostInput.setText(settings.http_host)

    def save_settings_to_file(self, fpath=False):
        """????????? ?????? `save_settings_to_file`."""
        self.save_config()

    def reset_settings(self):
        """?????????? ?????? `reset_settings`."""
        settings.reset_user_config()
        self.settings = settings
        self.load_ui_from_settings()
        self.ctrl.set_connection_mode(settings.connection_mode)
        if hasattr(self, "config_window"):
            self.config_window.tangoHostInput.setText(settings.tango_host)
            self.config_window.deviceProxyInput.setText(settings.device_proxy)
            self.config_window.httpHostInput.setText(settings.http_host)

    def save_config(self):
        """????????? ?????? `save_config`."""
        input_gains_state = self.inputGainsPanel.get_state() if hasattr(self, "inputGainsPanel") else {"ranges": {}, "auto_gain": {}}
        config = settings.build_runtime_config(
            connection_mode="tango" if self.tangocheck.isChecked() else "direct",
            tango_host=getattr(settings, "tango_host", ""),
            device_proxy=getattr(settings, "device_proxy", ""),
            http_host=getattr(settings, "http_host", ""),
            calibration_path=self.calibPathInput.text().strip(),
            data_path=self.sysDataPathInput.text().strip() or str(BASE_DIR / "results"),
            sample_rate=int(self.scanSampleRateInput.text()),
            mod_freq=float(self.freqInput.text()),
            mod_amp=float(self.amplitudeInput.text()),
            mod_offset=float(self.offsetInput.text()),
            input_gain_ranges=input_gains_state["ranges"],
            input_gain_auto=input_gains_state["auto_gain"],
        )

        settings.save_user_config(config)
        self.ctrl.set_connection_mode(settings.connection_mode)

    def closeEvent(self, event):
        """???????? ?????? `closeEvent`."""
        box = qt.QMessageBox(self)
        box.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        box.setWindowModality(qt.Qt.WindowModal)
        box.setIcon(qt.QMessageBox.Question)
        box.setWindowTitle("Save Config")
        box.setText("Save application settings before closing?")
        box.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No | qt.QMessageBox.Cancel)
        box.setDefaultButton(qt.QMessageBox.Yes)
        _center_on_parent(box, self)
        reply = box.exec()

        if reply == qt.QMessageBox.Cancel:
            event.ignore()
            return
        if reply == qt.QMessageBox.Yes:
            try:
                self.save_config()
            except Exception as exc:
                ErrorWindow(f"Failed to save config.json: {exc}", self)
                event.ignore()
                return
        super().closeEvent(event)
