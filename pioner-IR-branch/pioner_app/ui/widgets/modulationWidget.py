import csv
import time
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel
from silx.gui import qt

from pioner_app.core.basemath import DataProcessor, temperature_to_voltage
from pioner_app.hardware.daq_controller import get_daq_controller
from pioner_app.ui.localization import tr, apply_language


class DualAxisTrend(qt.QWidget):
    def __init__(
        self,
        left_name,
        left_color,
        right_name,
        right_color,
        left_unit='',
        right_unit='',
        left_fmt='{:.4f}',
        right_fmt='{:.4f}',
        parent=None,
    ):
        super().__init__(parent)

        self.left_name = left_name
        self.right_name = right_name
        self.left_color = left_color
        self.right_color = right_color
        self.left_unit = left_unit
        self.right_unit = right_unit
        self.left_fmt = left_fmt
        self.right_fmt = right_fmt
        self.x_name = 'Time'
        self.x_unit = ' s'
        self.x_fmt = '{:.4f}'
        self.aux_name = 'Power'
        self.aux_unit = ' W'
        self.aux_fmt = '{:.6f}'

        root = qt.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.plot = pg.PlotWidget()
        self.plot.setBackground('w')
        self.plot.showGrid(x=True, y=False, alpha=0.55)
        self.plot.getAxis('left').setPen(pg.mkPen(left_color, width=1.2))
        self.plot.getAxis('left').setTextPen(pg.mkPen(left_color, width=1.2))
        self.plot.getAxis('bottom').setPen(pg.mkPen('k', width=1.0))
        self.plot.getAxis('bottom').setTextPen(pg.mkPen('k', width=1.0))
        self.plot.getAxis('bottom').setStyle(tickTextOffset=4)
        self.plot.getAxis('left').setWidth(55)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.hideButtons()
        self.plot.getPlotItem().setContentsMargins(8, 8, 8, 8)
        self.plot.getPlotItem().getViewBox().setMouseMode(pg.ViewBox.PanMode)
        self.plot.setLabel('bottom', self.x_name, units=self.x_unit.strip())

        self.right_view = pg.ViewBox()
        self.right_view.setMouseEnabled(x=True, y=True)
        self.right_view.setMouseMode(pg.ViewBox.PanMode)
        self.plot.showAxis('right')
        self.plot.scene().addItem(self.right_view)
        self.plot.getAxis('right').linkToView(self.right_view)
        self.right_view.setXLink(self.plot)
        self.plot.getAxis('right').setPen(pg.mkPen(right_color, width=1.2))
        self.plot.getAxis('right').setTextPen(pg.mkPen(right_color, width=1.2))
        self.plot.getAxis('right').setWidth(55)
        self.plot.getPlotItem().vb.sigResized.connect(self._update_views)

        self.left_curve = self.plot.plot(pen=pg.mkPen(left_color, width=1.0, cosmetic=True))
        self.right_curve = pg.PlotCurveItem(pen=pg.mkPen(right_color, width=1.0, cosmetic=True))
        self.right_view.addItem(self.right_curve)

        self.left_zero = pg.InfiniteLine(angle=0, pen=pg.mkPen((0, 0, 0, 80), width=0.8))
        self.right_zero = pg.InfiniteLine(angle=0, pen=pg.mkPen((0, 0, 0, 80), width=0.8))
        self.plot.addItem(self.left_zero)
        self.right_view.addItem(self.right_zero)

        root.addWidget(self.plot, 1)

        side = qt.QVBoxLayout()
        side.setContentsMargins(0, 0, 2, 0)
        side.setSpacing(2)
        side.addSpacing(6)

        self.right_value = QLabel('--')
        self.right_value.setStyleSheet(f'color: {right_color}; font-size: 12px;')
        self.right_name_label = QLabel(right_name)
        self.right_name_label.setStyleSheet(f'color: {right_color}; font-size: 12px;')
        self.left_value = QLabel('--')
        self.left_value.setStyleSheet(f'color: {left_color}; font-size: 12px;')
        self.left_name_label = QLabel(left_name)
        self.left_name_label.setStyleSheet(f'color: {left_color}; font-size: 12px;')
        self.aux_value = QLabel('--')
        self.aux_value.setStyleSheet('color: black; font-size: 12px;')
        self.aux_name_label = QLabel(self.aux_name)
        self.aux_name_label.setStyleSheet('color: black; font-size: 12px;')

        side.addWidget(self.right_value, alignment=qt.Qt.AlignRight)
        side.addWidget(self.right_name_label, alignment=qt.Qt.AlignRight)
        side.addSpacing(4)
        side.addWidget(self.left_value, alignment=qt.Qt.AlignRight)
        side.addWidget(self.left_name_label, alignment=qt.Qt.AlignRight)
        side.addStretch()
        side.addWidget(self.aux_value, alignment=qt.Qt.AlignRight)
        side.addWidget(self.aux_name_label, alignment=qt.Qt.AlignRight)
        root.addLayout(side)

        self._update_views()

    def _format_value(self, value, fmt, unit):
        text = fmt.format(float(value))
        return f'{text}{unit}' if unit else text

    def _update_views(self):
        rect = self.plot.getPlotItem().vb.sceneBoundingRect()
        self.right_view.setGeometry(rect)
        self.right_view.linkedViewChanged(self.plot.getPlotItem().vb, self.right_view.XAxis)

    def set_x_axis(self, name, unit, fmt='{:.4f}'):
        self.x_name = name
        self.x_unit = unit
        self.x_fmt = fmt
        self.plot.setLabel('bottom', name, units=unit.strip() if unit else None)

    def set_aux_display(self, name, unit, fmt='{:.4f}'):
        self.aux_name = name
        self.aux_unit = unit
        self.aux_fmt = fmt
        label = name if not unit else f'{name} ({unit.strip()})'
        self.aux_name_label.setText(label)

    def set_data(self, x, left_y, right_y, aux_value=None):
        self.left_curve.setData(x, left_y)
        self.right_curve.setData(x, right_y)
        self._update_views()

        if len(left_y):
            left_last = float(left_y[-1])
            self.left_value.setText(self._format_value(left_last, self.left_fmt, self.left_unit))
            self.left_zero.setPos(left_last)
        else:
            self.left_value.setText('--')
            self.left_zero.setPos(0.0)

        if len(right_y):
            right_last = float(right_y[-1])
            self.right_value.setText(self._format_value(right_last, self.right_fmt, self.right_unit))
            self.right_zero.setPos(right_last)
        else:
            self.right_value.setText('--')
            self.right_zero.setPos(0.0)

        if aux_value is not None:
            self.aux_value.setText(self._format_value(float(aux_value), self.aux_fmt, self.aux_unit))
        else:
            self.aux_value.setText('--')


class SlowHeatingWidget(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.ctrl = get_daq_controller()
        self.processor = DataProcessor(calibration=self.ctrl.calibration)
        self.time_data = []
        self.x_data = []
        self.ttpl_data = []
        self.thtr_data = []
        self.amp_data = []
        self.phase_data = []
        self.power_data = []
        self._processed_points = 0
        self._analysis_buffer = np.empty((0, 0))
        self._run_meta = {}
        self._save_prompt_enabled = False
        self._amp_unit = ''
        self._amp_label = 'Amplitude'
        self._phase_offset_display = 0.0
        self._skip_display_points = 0
        self._syncing_x_range = False
        self._auto_follow_x = True

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_loop)

        self._build_ui()
        self._connect()
        self._ramp_mode_flag = 'temperature' if self.mode_temp.isChecked() else 'voltage'
        self._update_ramp_mode_labels()
        self._update_x_axis_mode()
        self._update_amplitude_presentation()
        apply_language(self)

    def _build_ui(self):
        root = qt.QHBoxLayout(self)
        left = qt.QVBoxLayout()

        self.mod_group = qt.QGroupBox('Modulation Ramps')
        mod_layout = qt.QGridLayout()
        self.mod_info = qt.QLabel('Modulation uses the main window frequency, amplitude and offset. Optional ramps below change frequency, amplitude and phase step-by-step during slow heating.')
        self.mod_info.setWordWrap(True)
        mod_layout.addWidget(self.mod_info, 0, 0, 1, 3)

        self.final_freq = qt.QLineEdit('0')
        self.final_amp = qt.QLineEdit('0')
        self.final_phase = qt.QLineEdit('0')
        self.freq_ramp_btn = qt.QPushButton('F-ramp')
        self.amp_ramp_btn = qt.QPushButton('A-ramp')
        self.phase_ramp_btn = qt.QPushButton('P-ramp')
        for button in (self.freq_ramp_btn, self.amp_ramp_btn, self.phase_ramp_btn):
            button.setCheckable(True)
        mod_layout.addWidget(qt.QLabel('Final Freq (Hz)'), 1, 0)
        mod_layout.addWidget(self.final_freq, 1, 1)
        mod_layout.addWidget(self.freq_ramp_btn, 1, 2)
        mod_layout.addWidget(qt.QLabel('Final Amp (mA)'), 2, 0)
        mod_layout.addWidget(self.final_amp, 2, 1)
        mod_layout.addWidget(self.amp_ramp_btn, 2, 2)
        mod_layout.addWidget(qt.QLabel('Final Phase (deg)'), 3, 0)
        mod_layout.addWidget(self.final_phase, 3, 1)
        mod_layout.addWidget(self.phase_ramp_btn, 3, 2)

        self.x2_freq_check = qt.QCheckBox('x2 demod')
        self.ramp_steps = qt.QSpinBox()
        self.ramp_steps.setRange(1, 10000)
        self.ramp_steps.setValue(10)
        mod_layout.addWidget(self.x2_freq_check, 4, 0, 1, 2)
        mod_layout.addWidget(qt.QLabel('Ramp steps'), 5, 0)
        mod_layout.addWidget(self.ramp_steps, 5, 1)
        self.mod_group.setLayout(mod_layout)
        left.addWidget(self.mod_group)

        self.heat_group = qt.QGroupBox('Slow Heating')
        heat_layout = qt.QGridLayout()
        self.mode_temp = qt.QRadioButton('Temperature ramp')
        self.mode_volt = qt.QRadioButton('Voltage ramp')
        self.mode_temp.setChecked(True)
        heat_layout.addWidget(self.mode_temp, 0, 0, 1, 2)
        heat_layout.addWidget(self.mode_volt, 1, 0, 1, 2)
        self.start_val = qt.QLineEdit('20')
        self.end_val = qt.QLineEdit('100')
        self.rate = qt.QLineEdit('1')
        self.start_label = qt.QLabel('Start (C)')
        self.end_label = qt.QLabel('End (C)')
        self.rate_label = qt.QLabel('Rate / min (C)')
        heat_layout.addWidget(self.start_label, 2, 0)
        heat_layout.addWidget(self.start_val, 2, 1)
        heat_layout.addWidget(self.end_label, 3, 0)
        heat_layout.addWidget(self.end_val, 3, 1)
        heat_layout.addWidget(self.rate_label, 4, 0)
        heat_layout.addWidget(self.rate, 4, 1)
        self.analysis_method = qt.QComboBox()
        self.analysis_method.addItems(['Lock-in', 'FFT'])
        self.periods_box = qt.QSpinBox()
        self.periods_box.setRange(1, 50)
        self.periods_box.setValue(8)
        self.point_interval_input = qt.QDoubleSpinBox()
        self.point_interval_input.setRange(0.25, 60.0)
        self.point_interval_input.setDecimals(2)
        self.point_interval_input.setSingleStep(0.25)
        self.point_interval_input.setValue(1.0)
        self.x_axis_mode = qt.QComboBox()
        self.x_axis_mode.addItems(['Time', 'AO1 Voltage', 'AO1 Temperature'])
        self.hold_final = qt.QCheckBox('Hold final value')
        heat_layout.addWidget(qt.QLabel('Analysis'), 5, 0)
        heat_layout.addWidget(self.analysis_method, 5, 1)
        heat_layout.addWidget(qt.QLabel('Periods / point'), 6, 0)
        heat_layout.addWidget(self.periods_box, 6, 1)
        heat_layout.addWidget(qt.QLabel('Point dt (s)'), 7, 0)
        heat_layout.addWidget(self.point_interval_input, 7, 1)
        heat_layout.addWidget(qt.QLabel('X axis'), 8, 0)
        heat_layout.addWidget(self.x_axis_mode, 8, 1)
        heat_layout.addWidget(self.hold_final, 9, 0, 1, 2)
        self.status_label = qt.QLabel('Idle')
        heat_layout.addWidget(self.status_label, 10, 0, 1, 2)
        self.start_btn = qt.QPushButton('START EXP')
        self.stop_btn = qt.QPushButton('STOP EXP')
        heat_layout.addWidget(self.start_btn, 11, 0)
        heat_layout.addWidget(self.stop_btn, 11, 1)
        self.heat_group.setLayout(heat_layout)
        left.addWidget(self.heat_group)
        left.addStretch()
        root.addLayout(left, 1)

        right = qt.QVBoxLayout()
        nav_layout = qt.QHBoxLayout()
        self.reset_view_btn = qt.QPushButton('Reset view')
        nav_layout.addStretch()
        nav_layout.addWidget(self.reset_view_btn)
        right.addLayout(nav_layout)
        self.lockin_trend = DualAxisTrend(
            'Amplitude',
            '#ff0000',
            'Phase',
            '#0000ff',
            left_unit='',
            right_unit=' deg',
            left_fmt='{:.5f}',
            right_fmt='{:.1f}',
        )
        self.temp_trend = DualAxisTrend(
            'Ttpl',
            '#ff0000',
            'Thtr',
            '#0000ff',
            left_unit=' C',
            right_unit=' C',
            left_fmt='{:.4f}',
            right_fmt='{:.4f}',
        )
        self.lockin_trend.set_aux_display('Power', ' W', '{:.6f}')
        self.temp_trend.set_aux_display('Power', ' W', '{:.6f}')
        right.addWidget(self.lockin_trend, 1)
        right.addWidget(self.temp_trend, 1)
        root.addLayout(right, 2)

    def _connect(self):
        self.start_btn.clicked.connect(self.start_SH_exp)
        self.stop_btn.clicked.connect(self.stop_all)
        self.mode_temp.toggled.connect(self._on_ramp_mode_toggled)
        self.mode_volt.toggled.connect(self._on_ramp_mode_toggled)
        self.x_axis_mode.currentIndexChanged.connect(self._update_x_axis_mode)
        self.reset_view_btn.clicked.connect(self._reset_view_ranges)
        self.lockin_trend.plot.getPlotItem().vb.sigXRangeChanged.connect(self._sync_x_from_lockin)
        self.temp_trend.plot.getPlotItem().vb.sigXRangeChanged.connect(self._sync_x_from_temp)

    def _main_window(self):
        return self.window()

    def _modulation_values(self):
        main = self._main_window()
        if main is None:
            raise RuntimeError('Main window is not available')
        return (
            float(main.freqInput.text() or 0),
            float(main.amplitudeInput.text() or 0),
            float(main.offsetInput.text() or 0),
        )

    def _modulation_ramp_config(self, freq, amp):
        return {
            'final_freq': float(self.final_freq.text() or freq),
            'final_amp': float(self.final_amp.text() or amp),
            'final_phase_deg': float(self.final_phase.text() or 0.0),
            'enable_freq_ramp': self.freq_ramp_btn.isChecked(),
            'enable_amp_ramp': self.amp_ramp_btn.isChecked(),
            'enable_phase_ramp': self.phase_ramp_btn.isChecked(),
            'ramp_steps': int(self.ramp_steps.value()),
            'x2_mode': bool(self.x2_freq_check.isChecked()),
        }

    def _append_buffer(self, data):
        raw = np.asarray(data)
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)
        if raw.size == 0:
            return
        if self._analysis_buffer.size == 0:
            self._analysis_buffer = raw.copy()
        else:
            self._analysis_buffer = np.vstack((self._analysis_buffer, raw))

    def _power_from_ao1_voltage(self, voltage):
        resistance = float(getattr(self.ctrl.calibration, 'rhtr', 0.0) or 0.0)
        if resistance <= 0:
            return 0.0
        return (float(voltage) ** 2) / resistance

    def _update_amplitude_presentation(self, unit=None):
        if unit is None:
            unit = 'C' if self.ctrl.calibration is not None else 'mV'
        self._amp_label = 'Amplitude, dT' if unit == 'C' else 'Amplitude'
        self._amp_unit = f' {unit}' if unit else ''
        self.lockin_trend.left_name = self._amp_label
        self.lockin_trend.left_unit = self._amp_unit
        self.lockin_trend.left_fmt = '{:.4f}' if unit == 'C' else '{:.5f}'
        self.lockin_trend.left_name_label.setText(self._amp_label)

    def _update_ramp_mode_labels(self):
        if self.mode_temp.isChecked():
            self.start_label.setText('Start (C)')
            self.end_label.setText('End (C)')
            self.rate_label.setText('Rate / min (C)')
        else:
            self.start_label.setText('Start (V)')
            self.end_label.setText('End (V)')
            self.rate_label.setText('Rate / min (V)')

    def _convert_ramp_value(self, value, to_mode):
        cal = getattr(self.ctrl, 'calibration', None)
        if cal is None:
            return value
        try:
            numeric = float(value)
        except Exception:
            return value
        if to_mode == 'temperature':
            return float(cal.theaterconv(numeric))
        return float(temperature_to_voltage(numeric, calibration=cal))

    def _on_ramp_mode_toggled(self):
        sender = self.sender()
        if sender is None or not sender.isChecked():
            self._update_ramp_mode_labels()
            return
        target_mode = 'temperature' if self.mode_temp.isChecked() else 'voltage'
        source_mode = 'voltage' if target_mode == 'temperature' else 'temperature'
        current_flag = getattr(self, '_ramp_mode_flag', source_mode)
        if current_flag != target_mode:
            try:
                self.start_val.setText(f"{self._convert_ramp_value(self.start_val.text(), target_mode):.6g}")
                self.end_val.setText(f"{self._convert_ramp_value(self.end_val.text(), target_mode):.6g}")
            except Exception:
                pass
        self._ramp_mode_flag = target_mode
        self._update_ramp_mode_labels()

    def _update_x_axis_mode(self):
        mode = self.x_axis_mode.currentText()
        if mode == 'AO1 Voltage':
            axis_name = 'AO1 Voltage'
            axis_unit = ' V'
            axis_fmt = '{:.4f}'
        elif mode == 'AO1 Temperature':
            axis_name = 'AO1 Temperature'
            axis_unit = ' C'
            axis_fmt = '{:.3f}'
        else:
            axis_name = 'Time'
            axis_unit = ' s'
            axis_fmt = '{:.4f}'
        self.lockin_trend.set_x_axis(axis_name, axis_unit, axis_fmt)
        self.temp_trend.set_x_axis(axis_name, axis_unit, axis_fmt)
        self._refresh_plots()

    def _ao1_setpoint_from_elapsed(self, elapsed_sec):
        meta = self._run_meta or {}
        mode = meta.get('mode')
        start_value = float(meta.get('start_value', 0.0))
        end_value = float(meta.get('end_value', start_value))
        rate_per_min = abs(float(meta.get('rate_per_min', 0.0)))
        if rate_per_min <= 0:
            value = start_value
        else:
            direction = 1.0 if end_value >= start_value else -1.0
            delta = direction * rate_per_min * (elapsed_sec / 60.0)
            value = start_value + delta
            if direction > 0:
                value = min(value, end_value)
            else:
                value = max(value, end_value)

        if meta.get('ramp_completed'):
            value = end_value

        if mode == 'temperature':
            return float(temperature_to_voltage(value, calibration=self.ctrl.calibration))
        return float(value)

    def _x_value_for_elapsed(self, elapsed_sec):
        mode = self.x_axis_mode.currentText()
        ao1_voltage = self._ao1_setpoint_from_elapsed(elapsed_sec)
        if mode == 'AO1 Voltage':
            return ao1_voltage
        if mode == 'AO1 Temperature':
            cal = getattr(self.ctrl, 'calibration', None)
            if cal is None:
                return ao1_voltage
            return float(cal.theaterconv(float(ao1_voltage)))
        return float(elapsed_sec)

    def _rebuild_x_data(self):
        self.x_data = [self._x_value_for_elapsed(t) for t in self.time_data]
        self.power_data = [self._power_from_ao1_voltage(self._ao1_setpoint_from_elapsed(t)) for t in self.time_data]

    def _refresh_plots(self):
        self._rebuild_x_data()
        aux_value = self.power_data[-1] if self.power_data else None
        self.lockin_trend.set_data(self.x_data, self.amp_data, self.phase_data, aux_value=aux_value)
        self.temp_trend.set_data(self.x_data, self.ttpl_data, self.thtr_data, aux_value=aux_value)

    def _apply_linked_x_range(self, source_plot, target_plot):
        if self._syncing_x_range:
            return
        self._syncing_x_range = True
        try:
            x_range, _ = source_plot.getPlotItem().vb.viewRange()
            target_plot.setXRange(float(x_range[0]), float(x_range[1]), padding=0.0)
        finally:
            self._syncing_x_range = False

    def _sync_x_from_lockin(self, *args):
        self._apply_linked_x_range(self.lockin_trend.plot, self.temp_trend.plot)

    def _sync_x_from_temp(self, *args):
        self._apply_linked_x_range(self.temp_trend.plot, self.lockin_trend.plot)

    def _reset_view_ranges(self):
        if not self.x_data:
            return
        x_min = float(min(self.x_data))
        x_max = float(max(self.x_data))
        if x_max <= x_min:
            x_max = x_min + 1.0

        def _safe_bounds(values):
            if not values:
                return -1.0, 1.0
            y_min = float(min(values))
            y_max = float(max(values))
            if y_max <= y_min:
                pad = 1.0 if y_min == 0 else abs(y_min) * 0.1
                y_min -= pad
                y_max += pad
            return y_min, y_max

        amp_min, amp_max = _safe_bounds(self.amp_data)
        phase_min, phase_max = _safe_bounds(self.phase_data)
        ttpl_min, ttpl_max = _safe_bounds(self.ttpl_data)
        thtr_min, thtr_max = _safe_bounds(self.thtr_data)

        self._syncing_x_range = True
        try:
            self.lockin_trend.plot.setXRange(x_min, x_max, padding=0.02)
            self.temp_trend.plot.setXRange(x_min, x_max, padding=0.02)
            self.lockin_trend.plot.setYRange(amp_min, amp_max, padding=0.05)
            self.lockin_trend.right_view.setYRange(phase_min, phase_max, padding=0.05)
            self.temp_trend.plot.setYRange(ttpl_min, ttpl_max, padding=0.05)
            self.temp_trend.right_view.setYRange(thtr_min, thtr_max, padding=0.05)
        finally:
            self._syncing_x_range = False

    def _autoscale_y_axes(self):
        if not self.x_data:
            return

        def _safe_bounds(values):
            if not values:
                return -1.0, 1.0
            y_min = float(min(values))
            y_max = float(max(values))
            if y_max <= y_min:
                pad = 1.0 if y_min == 0 else max(abs(y_min) * 0.1, 1e-6)
                y_min -= pad
                y_max += pad
            return y_min, y_max

        amp_min, amp_max = _safe_bounds(self.amp_data)
        phase_min, phase_max = _safe_bounds(self.phase_data)
        ttpl_min, ttpl_max = _safe_bounds(self.ttpl_data)
        thtr_min, thtr_max = _safe_bounds(self.thtr_data)

        self.lockin_trend.plot.setYRange(amp_min, amp_max, padding=0.05)
        self.lockin_trend.right_view.setYRange(phase_min, phase_max, padding=0.05)
        self.temp_trend.plot.setYRange(ttpl_min, ttpl_max, padding=0.05)
        self.temp_trend.right_view.setYRange(thtr_min, thtr_max, padding=0.05)

    def _follow_latest_x(self):
        if not self.x_data or not self._auto_follow_x:
            return
        x_last = float(self.x_data[-1])
        x_first = float(self.x_data[0])
        current_range, _ = self.lockin_trend.plot.getPlotItem().vb.viewRange()
        width = float(current_range[1] - current_range[0])
        if width <= 0:
            width = max(x_last - x_first, 1.0)
        target_left = max(x_first, x_last - width)
        target_right = max(x_last, target_left + width)
        self._syncing_x_range = True
        try:
            self.lockin_trend.plot.setXRange(target_left, target_right, padding=0.0)
            self.temp_trend.plot.setXRange(target_left, target_right, padding=0.0)
        finally:
            self._syncing_x_range = False

    def _point_interval_sec(self):
        chunk_size = int(self._run_meta.get('analysis_chunk_size', 0) or 0)
        sample_rate = self.ctrl.em.ai.sample_rate if self.ctrl and self.ctrl.em else 1
        if chunk_size <= 0 or sample_rate <= 0:
            return 0.0
        return chunk_size / float(sample_rate)

    def _phase_for_display(self, phase_deg):
        phase = float(phase_deg) + self._phase_offset_display
        while phase > 180.0:
            phase -= 360.0
        while phase < -180.0:
            phase += 360.0
        return phase

    def _append_point(self, metrics):
        point_interval = self._point_interval_sec()
        elapsed = (self._processed_points + 1) * point_interval
        self._processed_points += 1
        if self._processed_points <= int(self._skip_display_points):
            return

        display_elapsed = elapsed - (self._skip_display_points * point_interval)
        power_value = self._power_from_ao1_voltage(self._ao1_setpoint_from_elapsed(elapsed))

        self.time_data.append(display_elapsed)
        self.x_data.append(self._x_value_for_elapsed(elapsed))
        self.ttpl_data.append(metrics['Ttpl'])
        self.thtr_data.append(metrics['Thtr'])
        self.amp_data.append(metrics['amplitude'])
        self.phase_data.append(self._phase_for_display(metrics['phase']))
        self.power_data.append(power_value)

        self.lockin_trend.set_data(self.x_data, self.amp_data, self.phase_data, aux_value=power_value)
        self.temp_trend.set_data(self.x_data, self.ttpl_data, self.thtr_data, aux_value=power_value)
        if len(self.x_data) <= 2:
            self._reset_view_ranges()
        else:
            self._follow_latest_x()
            self._autoscale_y_axes()

    def start_SH_exp(self):
        try:
            freq, amp, offset = self._modulation_values()
            start = float(self.start_val.text() or 0)
            end = float(self.end_val.text() or 0)
            rate_per_min = float(self.rate.text() or 0)
            if rate_per_min == 0:
                raise ValueError('Slow heating rate cannot be zero')

            mode = 'temperature' if self.mode_temp.isChecked() else 'voltage'
            self.time_data.clear()
            self.x_data.clear()
            self.ttpl_data.clear()
            self.thtr_data.clear()
            self.amp_data.clear()
            self.phase_data.clear()
            self.power_data.clear()
            self._analysis_buffer = np.empty((0, 0))
            self._processed_points = 0
            self._phase_offset_display = 0.0
            self._skip_display_points = 0
            self._syncing_x_range = False
            self._auto_follow_x = True
            self._update_amplitude_presentation()
            self.processor = DataProcessor(
                calibration=self.ctrl.calibration,
                sample_rate=self.ctrl.em.ai.sample_rate if self.ctrl.em else None,
            )
            self._run_meta = self.ctrl.start_slow_heating(
                freq,
                amp,
                offset,
                mode,
                start,
                end,
                rate_per_min,
                hold_final_value=self.hold_final.isChecked(),
                demod_periods=self.periods_box.value(),
                modulation_ramps=self._modulation_ramp_config(freq, amp),
                point_interval_sec=float(self.point_interval_input.value()),
            )
            self._skip_display_points = int(self._run_meta.get('skip_display_points', 0) or 0)
            self._save_prompt_enabled = True
            self._update_x_axis_mode()
            if self._skip_display_points > 0:
                self.status_label.setText(tr('Zeroing outputs...'))
            else:
                self.status_label.setText(tr(f'Running {mode} ramp'))
            self.timer.start(100)
            self._reset_view_ranges()
        except Exception as exc:
            self.timer.stop()
            self.status_label.setText(tr(f'Slow heating start error: {exc}'))

    def _process_available_chunks(self):
        chunk_size = int(self._run_meta.get('analysis_chunk_size', 0) or 0)
        if chunk_size <= 0 or self._analysis_buffer.size == 0:
            return 0

        method = self.analysis_method.currentText().lower().replace('-', '')
        method = 'fft' if 'fft' in method else 'lockin'
        demod_freq = float(self._run_meta.get('demod_frequency', self._run_meta.get('freq', 0.0)))
        periods = int(self._run_meta.get('demod_periods', max(self.periods_box.value(), 3)))
        processed = 0

        while len(self._analysis_buffer) >= chunk_size:
            chunk = np.array(self._analysis_buffer[:chunk_size], copy=True)
            self._analysis_buffer = self._analysis_buffer[chunk_size:]
            metrics = self.processor.analyze_slow_heating_chunk(
                chunk,
                frequency=demod_freq,
                method=method,
                periods=periods,
                modulation_amp=float(self._run_meta.get('current_amp', self._run_meta.get('amp', 0.0)) or 0.0),
                x2_mode=bool((self._run_meta.get('modulation_ramps') or {}).get('x2_mode', False)),
            )
            if metrics is not None:
                self._update_amplitude_presentation(metrics.get('amplitude_unit'))
                self._append_point(metrics)
                processed += 1
        return processed

    def update_loop(self):
        try:
            data = self.ctrl.read_dataSH()
            if data is not None:
                self._append_buffer(data)

            current_meta = self.ctrl.get_slow_heating_meta()
            if current_meta:
                self._run_meta = current_meta

            processed = self._process_available_chunks()
            ramp_text = []
            if self.freq_ramp_btn.isChecked():
                ramp_text.append('F')
            if self.amp_ramp_btn.isChecked():
                ramp_text.append('A')
            if self.phase_ramp_btn.isChecked():
                ramp_text.append('P')
            ramp_suffix = '' if not ramp_text else f', ramps {"/".join(ramp_text)}'

            if self._run_meta.get('error'):
                self.stop_all(status=self._run_meta['error'])
            elif self._run_meta.get('completed') and not self._run_meta.get('hold_final_value') and processed == 0 and len(self._analysis_buffer) == 0:
                self.stop_all()
            elif self._processed_points < int(self._run_meta.get('skip_display_points', 0) or 0):
                self.status_label.setText(tr('Zeroing outputs...'))
            elif self._run_meta.get('ramp_completed') and self._run_meta.get('hold_final_value'):
                self.status_label.setText(tr(f'Holding final setpoint{ramp_suffix}'))
            else:
                freq = float(self._run_meta.get('carrier_frequency', self._run_meta.get('freq', 0.0)))
                demod = float(self._run_meta.get('demod_frequency', self._run_meta.get('freq', 0.0)))
                self.status_label.setText(tr(f'Running, f={freq:.3g} Hz, demod={demod:.3g} Hz{ramp_suffix}'))
        except Exception as exc:
            self.timer.stop()
            self.status_label.setText(tr(f'Slow heating runtime error: {exc}'))

    def _default_results_dir(self):
        main = self._main_window()
        if main is not None and hasattr(main, 'sysDataPathInput'):
            folder = main.sysDataPathInput.text().strip()
            if folder:
                return Path(folder)
        return Path.cwd()

    def _save_results_dialog(self):
        if not self.time_data:
            return
        default_dir = self._default_results_dir()
        default_dir.mkdir(parents=True, exist_ok=True)
        default_name = default_dir / f"slow_heating_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = qt.QFileDialog.getSaveFileName(
            self,
            tr('Save slow heating results'),
            str(default_name),
            tr('CSV files (*.csv)'),
        )
        if not path:
            return
        self._save_results_csv(Path(path))

    def _save_results_csv(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        amp_header = 'amplitude_c' if self._amp_unit.strip() == 'C' else 'amplitude_mv'
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['time_s', 'x_value', 'ttpl_c', 'thtr_c', amp_header, 'phase_deg', 'power_w'])
            for row in zip(self.time_data, self.x_data, self.ttpl_data, self.thtr_data, self.amp_data, self.phase_data, self.power_data):
                writer.writerow(row)
        self.status_label.setText(tr(f'Saved: {path.name}'))

    def stop_all(self, status='Stopped'):
        self.timer.stop()
        self.ctrl.stop_slow_heating()
        if isinstance(status, bool):
            status = 'Stopped'
        self.status_label.setText(tr(str(status)))
        should_prompt = self._save_prompt_enabled and len(self.time_data) > 0
        self._save_prompt_enabled = False
        if should_prompt:
            self._save_results_dialog()



