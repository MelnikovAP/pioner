import time
from pathlib import Path
import numpy as np
import pyqtgraph as pg

from silx.gui import qt
from PyQt5.QtCore import QTimer

from pioner_app.core.basemath import DataProcessor
from pioner_app.paths import PROJECT_ROOT
from pioner_app.core.calibration import Calibration
from pioner_app.ui.localization import tr
from pioner_app.ui.widgets.input_gains_panel import InputGainsPanel
from pioner_app.ui.widgets.modulationWidget import DualAxisTrend


BACK_CODE = 2


class CalibrationSetupDialog(qt.QDialog):
    """Collects user inputs required to start the calibration workflow."""

    def __init__(self, parent=None, initial_config=None):
        super().__init__(parent)
        self.initial_config = dict(initial_config or {})
        self.setWindowTitle(tr('Calibration setup'))
        self.resize(760, 620)
        self.setWindowModality(qt.Qt.WindowModal)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._fill_defaults()

    def _build_ui(self):
        root = qt.QVBoxLayout(self)

        intro = qt.QLabel(tr('Enter calibrants, room temperature and slow-heating parameters for the calibration run.'))
        intro.setWordWrap(True)
        root.addWidget(intro)

        reset_info = qt.QLabel(tr('The calibration workflow will reset coefficients to default_calibration.json before the first run.'))
        reset_info.setWordWrap(True)
        reset_info.setStyleSheet('color: #8a6d3b; background: #fcf8e3; padding: 6px; border: 1px solid #faebcc; border-radius: 4px;')
        root.addWidget(reset_info)

        self.calibrants_table = qt.QTableWidget(4, 2)
        self.calibrants_table.setHorizontalHeaderLabels([tr('Calibrant'), tr('Melting temp (C)')])
        self.calibrants_table.horizontalHeader().setStretchLastSection(True)
        self.calibrants_table.verticalHeader().setVisible(False)
        root.addWidget(self.calibrants_table)

        table_buttons = qt.QHBoxLayout()
        self.add_row_button = qt.QPushButton(tr('Add row'))
        self.remove_row_button = qt.QPushButton(tr('Remove row'))
        table_buttons.addWidget(self.add_row_button)
        table_buttons.addWidget(self.remove_row_button)
        table_buttons.addStretch(1)
        root.addLayout(table_buttons)

        form = qt.QGridLayout()
        row = 0
        self.room_temp_input = qt.QLineEdit()
        self.safe_voltage_input = qt.QLineEdit()
        self.r_inner_input = qt.QLineEdit()
        self.r_guard_input = qt.QLineEdit()
        self.rate_input = qt.QLineEdit()
        self.temp_rate_input = qt.QLineEdit()

        for label, widget in [
            (tr('Room temperature (C)'), self.room_temp_input),
            (tr('Heater safe voltage (V)'), self.safe_voltage_input),
            (tr('R inner (Ohm)'), self.r_inner_input),
            (tr('R guard (Ohm)'), self.r_guard_input),
            (tr('Slow heating rate (V/min)'), self.rate_input),
            (tr('Temperature fit ramp rate (C/min)'), self.temp_rate_input),
        ]:
            form.addWidget(qt.QLabel(label), row, 0)
            form.addWidget(widget, row, 1)
            row += 1
        root.addLayout(form)

        gains_box = qt.QGroupBox(tr('Input gains'))
        gains_layout = qt.QVBoxLayout(gains_box)
        self.input_gains = InputGainsPanel()
        gains_layout.addWidget(self.input_gains)
        root.addWidget(gains_box)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = qt.QPushButton(tr('Cancel'))
        self.start_button = qt.QPushButton(tr('Start'))
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.start_button)
        root.addLayout(buttons)

        self.add_row_button.clicked.connect(self._add_row)
        self.remove_row_button.clicked.connect(self._remove_row)
        self.cancel_button.clicked.connect(self.reject)
        self.start_button.clicked.connect(self._accept_if_valid)

    def _fill_defaults(self):
        defaults = [
            ('In', '156.6'),
            ('Sn', '231.9'),
            ('Bi', '271.4'),
            ('Pb', '327.5'),
        ]
        initial_calibrants = list(self.initial_config.get('calibrants') or [])
        rows = max(len(initial_calibrants), len(defaults), 1)
        self.calibrants_table.setRowCount(rows)
        source = initial_calibrants or [{'name': name, 'temperature': float(temp)} for name, temp in defaults]
        for row, item in enumerate(source):
            self.calibrants_table.setItem(row, 0, qt.QTableWidgetItem(str(item.get('name', ''))))
            self.calibrants_table.setItem(row, 1, qt.QTableWidgetItem(str(item.get('temperature', ''))))

        parent = self.parent()
        calib = getattr(parent, 'calibration', None)
        self.room_temp_input.setText(str(self.initial_config.get('room_temperature', 25.0)))
        self.safe_voltage_input.setText(str(self.initial_config.get('safe_voltage', getattr(calib, 'safe_voltage', 5.0))))
        self.r_inner_input.setText(str(self.initial_config.get('r_inner', getattr(calib, 'rhtr', 0.0))))
        self.r_guard_input.setText(str(self.initial_config.get('r_guard', getattr(calib, 'rghtr', 0.0))))
        self.rate_input.setText(str(self.initial_config.get('rate_per_min', 0.5)))
        self.temp_rate_input.setText(str(self.initial_config.get('temp_rate_per_min', 15.0)))

        if 'input_gains' in self.initial_config:
            self.input_gains.set_state(**self.initial_config['input_gains'])
        elif parent is not None and hasattr(parent, 'inputGainsPanel'):
            self.input_gains.set_state(**parent.inputGainsPanel.get_state())

    def _add_row(self):
        self.calibrants_table.insertRow(self.calibrants_table.rowCount())

    def _remove_row(self):
        if self.calibrants_table.rowCount() > 1:
            self.calibrants_table.removeRow(self.calibrants_table.rowCount() - 1)

    def _accept_if_valid(self):
        try:
            self.get_config()
        except Exception as exc:
            qt.QMessageBox.warning(self, tr('Calibration setup'), str(exc))
            return
        self.accept()

    def get_config(self):
        calibrants = []
        for row in range(self.calibrants_table.rowCount()):
            name_item = self.calibrants_table.item(row, 0)
            temp_item = self.calibrants_table.item(row, 1)
            name = (name_item.text().strip() if name_item else '')
            temp_text = (temp_item.text().strip() if temp_item else '')
            if not name and not temp_text:
                continue
            if not name:
                raise ValueError(tr('Each calibrant row must have a name.'))
            if not temp_text:
                raise ValueError(tr('Each calibrant row must have a melting temperature.'))
            calibrants.append({'name': name, 'temperature': float(temp_text)})

        if not calibrants:
            raise ValueError(tr('Add at least one calibrant.'))

        return {
            'calibrants': calibrants,
            'room_temperature': float(self.room_temp_input.text() or 0.0),
            'safe_voltage': float(self.safe_voltage_input.text() or 0.0),
            'r_inner': float(self.r_inner_input.text() or 0.0),
            'r_guard': float(self.r_guard_input.text() or 0.0),
            'rate_per_min': float(self.rate_input.text() or 0.0),
            'temp_rate_per_min': float(self.temp_rate_input.text() or 15.0),
            'input_gains': self.input_gains.get_state(),
        }


class CalibrationRunDialog(qt.QDialog):
    """Runs a slow-heating ramp and collects calibration points."""

    def __init__(self, parent, title, config, allow_back=True, run_mode='voltage', start_value=0.0, end_value=None, rate_per_min=None):
        super().__init__(parent)
        self.main = parent
        self.ctrl = parent.ctrl
        self.processor = DataProcessor(calibration=self.ctrl.calibration, sample_rate=self.ctrl.em.ai.sample_rate if self.ctrl.em else None)
        self.config = dict(config)
        self.allow_back = bool(allow_back)
        self.run_mode = str(run_mode)
        self.start_value = float(start_value)
        self.end_value = None if end_value is None else float(end_value)
        self.rate_per_min = None if rate_per_min is None else float(rate_per_min)
        self._run_meta = {}
        self._analysis_buffer = np.empty((0, 0))
        self._processed_points = 0
        self._skip_display_points = 0
        self._result = None
        self._cancel_requested = False
        self._completed_at = None
        self._last_data_at = None

        self.time_data = []
        self.voltage_data = []
        self.ttpl_data = []
        self.thtr_data = []
        self.thtrd_data = []
        self.amp_data = []
        self.phase_data = []
        self.power_data = []
        self.uhtr_data = []
        self.utpl_raw_data = []
        self.uhtr_raw_data = []
        self.ihtr_raw_data = []
        self.rhtr_data = []

        self.setWindowTitle(title)
        self.resize(1100, 720)
        self.setWindowModality(qt.Qt.WindowModal)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_loop)
        QTimer.singleShot(0, self._start_run)

    def _build_ui(self):
        root = qt.QVBoxLayout(self)
        self.status_label = qt.QLabel(tr('Preparing calibration run...'))
        root.addWidget(self.status_label)
        self.progress_bar = qt.QProgressBar()
        self.progress_bar.setRange(0, 100)
        root.addWidget(self.progress_bar)

        self.lockin_trend = DualAxisTrend(
            'Amplitude', '#ff0000', 'Phase', '#0000ff', left_unit=' C', right_unit=' deg', left_fmt='{:.4f}', right_fmt='{:.2f}'
        )
        self.temp_trend = DualAxisTrend(
            'Ttpl', '#ff0000', 'Thtr', '#0000ff', left_unit=' C', right_unit=' C', left_fmt='{:.4f}', right_fmt='{:.4f}'
        )
        self.lockin_trend.set_x_axis('AO1 Voltage', ' V', '{:.4f}')
        self.temp_trend.set_x_axis('AO1 Voltage', ' V', '{:.4f}')
        self.lockin_trend.set_aux_display('Power', ' W', '{:.6f}')
        self.temp_trend.set_aux_display('Power', ' W', '{:.6f}')
        root.addWidget(self.lockin_trend, 1)
        root.addWidget(self.temp_trend, 1)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = qt.QPushButton(tr('Back'))
        self.back_button.setEnabled(self.allow_back)
        self.cancel_button = qt.QPushButton(tr('Cancel'))
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.cancel_button)
        root.addLayout(buttons)
        self.back_button.clicked.connect(self._go_back)
        self.cancel_button.clicked.connect(self._cancel)

    def _modulation_values(self):
        return (
            float(self.main.freqInput.text() or 0),
            float(self.main.amplitudeInput.text() or 0),
            float(self.main.offsetInput.text() or 0),
        )

    def _append_buffer(self, data):
        self._last_data_at = time.monotonic()
        raw = np.asarray(data)
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)
        if raw.size == 0:
            return
        if self._analysis_buffer.size == 0:
            self._analysis_buffer = raw.copy()
        else:
            self._analysis_buffer = np.vstack((self._analysis_buffer, raw))

    def _point_interval_sec(self):
        chunk_size = int(self._run_meta.get('analysis_chunk_size', 0) or 0)
        sample_rate = self.ctrl.em.ai.sample_rate if self.ctrl and self.ctrl.em else 1
        if chunk_size <= 0 or sample_rate <= 0:
            return 0.0
        return chunk_size / float(sample_rate)

    def _ao1_setpoint_from_elapsed(self, elapsed_sec):
        start_value = float(self._run_meta.get('start_value', 0.0))
        end_value = float(self._run_meta.get('end_value', start_value))
        rate_per_min = abs(float(self._run_meta.get('rate_per_min', 0.0)))
        if rate_per_min <= 0:
            return start_value
        delta = rate_per_min * (elapsed_sec / 60.0)
        value = start_value + delta
        return min(value, end_value)

    def _refresh_plots(self):
        aux = self.power_data[-1] if self.power_data else None
        self.lockin_trend.set_data(self.voltage_data, self.amp_data, self.phase_data, aux_value=aux)
        self.temp_trend.set_data(self.voltage_data, self.ttpl_data, self.thtr_data, aux_value=aux)

    def _autoscale(self):
        if not self.voltage_data:
            return

        def bounds(values):
            arr = np.asarray(values, dtype=float)
            if arr.size == 0:
                return -1.0, 1.0
            lo = float(np.min(arr))
            hi = float(np.max(arr))
            if hi <= lo:
                pad = 1.0 if lo == 0 else max(abs(lo) * 0.1, 1e-6)
                lo -= pad
                hi += pad
            return lo, hi

        x0, x1 = bounds(self.voltage_data)
        a0, a1 = bounds(self.amp_data)
        p0, p1 = bounds(self.phase_data)
        t0, t1 = bounds(self.ttpl_data)
        h0, h1 = bounds(self.thtr_data)
        self.lockin_trend.plot.setXRange(x0, x1, padding=0.02)
        self.temp_trend.plot.setXRange(x0, x1, padding=0.02)
        self.lockin_trend.plot.setYRange(a0, a1, padding=0.05)
        self.lockin_trend.right_view.setYRange(p0, p1, padding=0.05)
        self.temp_trend.plot.setYRange(t0, t1, padding=0.05)
        self.temp_trend.right_view.setYRange(h0, h1, padding=0.05)

    def _append_point(self, metrics):
        point_interval = self._point_interval_sec()
        elapsed = (self._processed_points + 1) * point_interval
        self._processed_points += 1
        if self._processed_points <= int(self._skip_display_points):
            return

        display_elapsed = elapsed - (self._skip_display_points * point_interval)
        ao1_voltage = self._ao1_setpoint_from_elapsed(elapsed)
        self.time_data.append(display_elapsed)
        self.voltage_data.append(ao1_voltage)
        self.utpl_raw_data.append(float(metrics.get('UtplRaw', 0.0)))
        self.uhtr_raw_data.append(float(metrics.get('UhtrRaw', 0.0)))
        self.ihtr_raw_data.append(float(metrics.get('IhtrRaw', 0.0)))
        self.rhtr_data.append(float(metrics.get('Rhtr', 0.0)))
        self.ttpl_data.append(float(metrics['Ttpl']))
        self.thtr_data.append(float(metrics['Thtr']))
        self.thtrd_data.append(float(metrics['Thtrd']))
        self.amp_data.append(float(metrics['amplitude']))
        phase = float(metrics['phase'])
        while phase > 180.0:
            phase -= 360.0
        while phase < -180.0:
            phase += 360.0
        self.phase_data.append(phase)
        self.power_data.append(float(metrics['power']))
        self.uhtr_data.append(float(metrics['Uhtr']))
        self._refresh_plots()
        self._autoscale()

    def _process_available_chunks(self):
        chunk_size = int(self._run_meta.get('analysis_chunk_size', 0) or 0)
        if chunk_size <= 0 or self._analysis_buffer.size == 0:
            return 0

        demod_freq = float(self._run_meta.get('demod_frequency', self._run_meta.get('freq', 0.0)))
        periods = int(self._run_meta.get('demod_periods', 8))
        processed = 0
        while len(self._analysis_buffer) >= chunk_size:
            chunk = np.array(self._analysis_buffer[:chunk_size], copy=True)
            self._analysis_buffer = self._analysis_buffer[chunk_size:]
            metrics = self.processor.analyze_slow_heating_chunk(
                chunk,
                frequency=demod_freq,
                method='lockin',
                periods=periods,
                modulation_amp=float(self._run_meta.get('current_amp', self._run_meta.get('amp', 0.0)) or 0.0),
                x2_mode=bool((self._run_meta.get('modulation_ramps') or {}).get('x2_mode', False)),
            )
            if metrics is not None:
                self._append_point(metrics)
                processed += 1
        return processed

    def _start_run(self):
        try:
            freq, amp, offset = self._modulation_values()
            end_value = self.end_value
            if end_value is None:
                end_value = float(self.config['safe_voltage']) if self.run_mode == 'voltage' else float(self.main.calibration.theaterconv(float(self.config['safe_voltage'])))
            rate_per_min = self.rate_per_min
            if rate_per_min is None:
                rate_per_min = float(self.config['rate_per_min']) if self.run_mode == 'voltage' else float(self.config.get('temp_rate_per_min', 15.0))
            self._run_meta = self.ctrl.start_slow_heating(
                freq,
                amp,
                offset,
                self.run_mode,
                float(self.start_value),
                float(end_value),
                float(rate_per_min),
                hold_final_value=False,
                demod_periods=8,
                modulation_ramps={
                    'final_freq': freq,
                    'final_amp': amp,
                    'final_phase_deg': 0.0,
                    'enable_freq_ramp': False,
                    'enable_amp_ramp': False,
                    'enable_phase_ramp': False,
                    'ramp_steps': 1,
                    'x2_mode': False,
                },
                point_interval_sec=1.0,
            )
            self._skip_display_points = int(self._run_meta.get('skip_display_points', 0) or 0)
            self.status_label.setText(tr('Calibration slow heating is running...'))
            self.timer.start(100)
        except Exception as exc:
            qt.QMessageBox.critical(self, tr('Calibration run'), str(exc))
            self.reject()

    def _finish_success(self):
        self.timer.stop()
        self.ctrl.stop_slow_heating()
        self._completed_at = None
        self._result = {
            'time_s': np.asarray(self.time_data, dtype=float),
            'ao1_voltage': np.asarray(self.voltage_data, dtype=float),
            'Ttpl': np.asarray(self.ttpl_data, dtype=float),
            'Thtr': np.asarray(self.thtr_data, dtype=float),
            'Thtrd': np.asarray(self.thtrd_data, dtype=float),
            'amplitude': np.asarray(self.amp_data, dtype=float),
            'phase': np.asarray(self.phase_data, dtype=float),
            'power': np.asarray(self.power_data, dtype=float),
            'Uhtr': np.asarray(self.uhtr_data, dtype=float),
            'UtplRaw': np.asarray(self.utpl_raw_data, dtype=float),
            'UhtrRaw': np.asarray(self.uhtr_raw_data, dtype=float),
            'IhtrRaw': np.asarray(self.ihtr_raw_data, dtype=float),
            'Rhtr': np.asarray(self.rhtr_data, dtype=float),
        }
        self.accept()

    def _go_back(self):
        self.timer.stop()
        try:
            self.ctrl.stop_slow_heating()
        finally:
            self.done(BACK_CODE)

    def _cancel(self):
        self._cancel_requested = True
        self.timer.stop()
        try:
            self.ctrl.stop_slow_heating()
        finally:
            self.reject()

    def _update_loop(self):
        data = self.ctrl.read_dataSH()
        if data is not None:
            self._append_buffer(data)

        current_meta = self.ctrl.get_slow_heating_meta()
        if current_meta:
            self._run_meta = current_meta

        self._process_available_chunks()
        duration = float(self._run_meta.get('duration_sec', 0.0) or 0.0)
        elapsed = self.time_data[-1] if self.time_data else 0.0
        if duration > 0:
            self.progress_bar.setValue(int(max(0.0, min(100.0, (elapsed / duration) * 100.0))))

        if self._run_meta.get('error'):
            self.timer.stop()
            self.ctrl.stop_slow_heating()
            qt.QMessageBox.critical(self, tr('Calibration run'), str(self._run_meta['error']))
            self.reject()
            return

        if self._run_meta.get('completed'):
            if self._completed_at is None:
                self._completed_at = time.monotonic()
            idle_for = 0.0 if self._last_data_at is None else time.monotonic() - self._last_data_at
            done_for = time.monotonic() - self._completed_at
            if len(self._analysis_buffer) == 0 or done_for >= 0.75 or idle_for >= 0.5:
                self._finish_success()

    def result_data(self):
        return self._result


class CalibrationCursorDialog(qt.QDialog):
    """Lets the user align cursor positions on amplitude curves to reference temperatures."""

    def __init__(self, parent, run_data, references, preset_points=None):
        super().__init__(parent)
        self.run_data = run_data
        self.references = sorted(references, key=lambda item: item['temperature'])
        self.preset_points = {item['name']: item for item in (preset_points or [])}
        self._cursor_pairs = []
        self.setWindowTitle(tr('Calibration cursor placement'))
        self.resize(1200, 760)
        self.setWindowModality(qt.Qt.WindowModal)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._build_cursors()

    def _build_ui(self):
        root = qt.QVBoxLayout(self)
        info = qt.QLabel(tr('Move the cursors to the peaks corresponding to room temperature and calibrant melting points, then press Next.'))
        info.setWordWrap(True)
        root.addWidget(info)

        plots = qt.QHBoxLayout()
        root.addLayout(plots, 1)

        self.plot_thtr = pg.PlotWidget(background='w')
        self.plot_thtr.setLabel('bottom', 'Thtr', units='C')
        self.plot_thtr.setLabel('left', 'Amplitude', units='C')
        self.plot_thtr.showGrid(x=True, y=True, alpha=0.3)
        self.plot_thtr.plot(self.run_data['Thtr'], self.run_data['amplitude'], pen=pg.mkPen('#d62728', width=1.5))
        plots.addWidget(self.plot_thtr, 1)

        self.plot_thtrd = pg.PlotWidget(background='w')
        self.plot_thtrd.setLabel('bottom', 'Thtrd', units='C')
        self.plot_thtrd.setLabel('left', 'Amplitude', units='C')
        self.plot_thtrd.showGrid(x=True, y=True, alpha=0.3)
        self.plot_thtrd.plot(self.run_data['Thtrd'], self.run_data['amplitude'], pen=pg.mkPen('#1f77b4', width=1.5))
        plots.addWidget(self.plot_thtrd, 1)

        self.table = qt.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr('Point'), tr('Reference T (C)'), tr('Thtr cursor'), tr('Thtrd cursor'), tr('Color')])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = qt.QPushButton(tr('Back'))
        self.cancel_button = qt.QPushButton(tr('Cancel'))
        self.next_button = qt.QPushButton(tr('Next'))
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.next_button)
        root.addLayout(buttons)
        self.back_button.clicked.connect(lambda: self.done(BACK_CODE))
        self.cancel_button.clicked.connect(self.reject)
        self.next_button.clicked.connect(self.accept)

    def _nearest_value(self, values, target):
        arr = np.asarray(values, dtype=float)
        if arr.size == 0:
            return float(target)
        idx = int(np.argmin(np.abs(arr - target)))
        return float(arr[idx])

    def _build_cursors(self):
        colors = ['#d62728', '#1f77b4', '#2ca02c', '#9467bd', '#ff7f0e', '#8c564b']
        for idx, ref in enumerate(self.references):
            color = colors[idx % len(colors)]
            preset = self.preset_points.get(ref['name'], {})
            thtr_pos = float(preset.get('thtr', self._nearest_value(self.run_data['Thtr'], ref['temperature'])))
            thtrd_pos = float(preset.get('thtrd', self._nearest_value(self.run_data['Thtrd'], ref['temperature'])))
            thtr_line = pg.InfiniteLine(pos=thtr_pos, angle=90, movable=True, pen=pg.mkPen(color, width=2))
            thtrd_line = pg.InfiniteLine(pos=thtrd_pos, angle=90, movable=True, pen=pg.mkPen(color, width=2))
            self.plot_thtr.addItem(thtr_line)
            self.plot_thtrd.addItem(thtrd_line)
            self._cursor_pairs.append((ref, thtr_line, thtrd_line, color))

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, qt.QTableWidgetItem(ref['name']))
            self.table.setItem(row, 1, qt.QTableWidgetItem(f"{ref['temperature']:.3f}"))
            self.table.setItem(row, 2, qt.QTableWidgetItem(f"{thtr_pos:.3f}"))
            self.table.setItem(row, 3, qt.QTableWidgetItem(f"{thtrd_pos:.3f}"))
            color_item = qt.QTableWidgetItem(color)
            color_item.setBackground(qt.QColor(color))
            self.table.setItem(row, 4, color_item)

            thtr_line.sigPositionChanged.connect(lambda _, r=row: self._update_row_values(r))
            thtrd_line.sigPositionChanged.connect(lambda _, r=row: self._update_row_values(r))

    def _update_row_values(self, row):
        ref, thtr_line, thtrd_line, _ = self._cursor_pairs[row]
        self.table.item(row, 2).setText(f"{thtr_line.value():.3f}")
        self.table.item(row, 3).setText(f"{thtrd_line.value():.3f}")

    def selected_points(self):
        points = []
        for ref, thtr_line, thtrd_line, color in self._cursor_pairs:
            points.append({
                'name': ref['name'],
                'temperature': float(ref['temperature']),
                'thtr': float(thtr_line.value()),
                'thtrd': float(thtrd_line.value()),
                'color': color,
            })
        return points


class CalibrationPolynomialDialog(qt.QDialog):
    """Fits quadratic temperature calibration from selected cursor points."""

    def __init__(self, parent, selected_points):
        super().__init__(parent)
        self.selected_points = list(selected_points)
        self._result = None
        self.setWindowTitle(tr('Calibration polynomial fit'))
        self.resize(1200, 760)
        self.setWindowModality(qt.Qt.WindowModal)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._fit()

    def _build_ui(self):
        root = qt.QVBoxLayout(self)
        info = qt.QLabel(tr('Measured cursor positions are shown against reference temperatures. Review the fit and apply the coefficients.'))
        info.setWordWrap(True)
        root.addWidget(info)

        plots = qt.QHBoxLayout()
        root.addLayout(plots, 1)
        self.plot_thtr = pg.PlotWidget(background='w')
        self.plot_thtr.setLabel('bottom', 'Measured Thtr', units='C')
        self.plot_thtr.setLabel('left', 'Reference temperature', units='C')
        self.plot_thtr.showGrid(x=True, y=True, alpha=0.3)
        plots.addWidget(self.plot_thtr, 1)

        self.plot_thtrd = pg.PlotWidget(background='w')
        self.plot_thtrd.setLabel('bottom', 'Measured Thtrd', units='C')
        self.plot_thtrd.setLabel('left', 'Reference temperature', units='C')
        self.plot_thtrd.showGrid(x=True, y=True, alpha=0.3)
        plots.addWidget(self.plot_thtrd, 1)

        coeffs = qt.QGridLayout()
        self.thtr_coeff_label = qt.QLabel('--')
        self.thtrd_coeff_label = qt.QLabel('--')
        coeffs.addWidget(qt.QLabel(tr('Thtr coefficients (k0, k1, k2)')), 0, 0)
        coeffs.addWidget(self.thtr_coeff_label, 0, 1)
        coeffs.addWidget(qt.QLabel(tr('Thtrd coefficients (k0, k1, k2)')), 1, 0)
        coeffs.addWidget(self.thtrd_coeff_label, 1, 1)
        root.addLayout(coeffs)

        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = qt.QPushButton(tr('Back'))
        self.cancel_button = qt.QPushButton(tr('Cancel'))
        self.apply_button = qt.QPushButton(tr('Apply and continue'))
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        root.addLayout(buttons)
        self.back_button.clicked.connect(lambda: self.done(BACK_CODE))
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self._accept)

    def _fit_one(self, x_values, y_values):
        x = np.asarray(x_values, dtype=float)
        y = np.asarray(y_values, dtype=float)
        if x.size == 0:
            return np.zeros(3, dtype=float)
        degree = 2 if len(x) >= 3 else max(0, len(x) - 1)
        design = [np.ones_like(x)]
        if degree >= 1:
            design.append(x)
        if degree >= 2:
            design.append(x ** 2)
        matrix = np.column_stack(design)
        coeffs, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        if coeffs.size < 3:
            coeffs = np.pad(coeffs, (0, 3 - coeffs.size), mode='constant')
        return coeffs

    def _fit(self):
        true_temp = np.asarray([item['temperature'] for item in self.selected_points], dtype=float)
        thtr = np.asarray([item['thtr'] for item in self.selected_points], dtype=float)
        thtrd = np.asarray([item['thtrd'] for item in self.selected_points], dtype=float)

        thtr_coeffs = self._fit_one(thtr, true_temp)
        thtrd_coeffs = self._fit_one(thtrd, true_temp)
        self._result = {
            'thtr': tuple(float(v) for v in thtr_coeffs),
            'thtrd': tuple(float(v) for v in thtrd_coeffs),
        }

        self.thtr_coeff_label.setText(', '.join(f'{v:.6g}' for v in self._result['thtr']))
        self.thtrd_coeff_label.setText(', '.join(f'{v:.6g}' for v in self._result['thtrd']))

        scatter_pen = pg.mkPen(None)
        scatter_brush = pg.mkBrush('#1f77b4')
        self.plot_thtr.addItem(pg.ScatterPlotItem(thtr, true_temp, pen=scatter_pen, brush=scatter_brush, size=9))
        self.plot_thtrd.addItem(pg.ScatterPlotItem(thtrd, true_temp, pen=scatter_pen, brush=scatter_brush, size=9))

        for plot, x, coeffs in ((self.plot_thtr, thtr, thtr_coeffs), (self.plot_thtrd, thtrd, thtrd_coeffs)):
            x_sorted = np.linspace(np.min(x), np.max(x), 300) if len(x) > 1 else np.asarray(x)
            y_fit = coeffs[0] + coeffs[1] * x_sorted + coeffs[2] * (x_sorted ** 2)
            plot.plot(x_sorted, y_fit, pen=pg.mkPen('#d62728', width=2))

    def _accept(self):
        self.accept()

    def coefficients(self):
        return self._result


class HeaterFitDialog(qt.QDialog):
    """Fits Theater(Uheater) = k1*U + k2*U^2 + k3*U^3 without a free term."""

    def __init__(self, parent, run_data):
        super().__init__(parent)
        self.run_data = run_data
        self._result = None
        self._x_full = None
        self._y_full = None
        self.region = None
        self.setWindowTitle(tr('Heater fit'))
        self.resize(960, 700)
        self.setWindowModality(qt.Qt.WindowModal)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._prepare_data()
        self._fit()

    def _build_ui(self):
        root = qt.QVBoxLayout(self)
        info = qt.QLabel(tr('Fit Thtrd versus AO1 heater voltage in the selected range and apply k1, k2, k3 to Theater(Uheater).'))
        info.setWordWrap(True)
        root.addWidget(info)
        self.plot = pg.PlotWidget(background='w')
        self.plot.setLabel('bottom', 'Uheater (AO1)', units='V')
        self.plot.setLabel('left', 'Thtrd', units='C')
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        root.addWidget(self.plot, 1)
        self.range_label = qt.QLabel('--')
        root.addWidget(self.range_label)
        self.coeff_label = qt.QLabel('--')
        root.addWidget(self.coeff_label)
        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = qt.QPushButton(tr('Back'))
        self.cancel_button = qt.QPushButton(tr('Cancel'))
        self.apply_button = qt.QPushButton(tr('Apply coefficients'))
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        root.addLayout(buttons)
        self.back_button.clicked.connect(lambda: self.done(BACK_CODE))
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)

    def _prepare_data(self):
        x = np.asarray(self.run_data['ao1_voltage'], dtype=float)
        y = np.asarray(self.run_data['Thtrd'], dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x = x[mask]
        y = y[mask]
        if x.size < 3:
            raise ValueError(tr('Not enough points to fit Theater(Uheater).'))
        self._x_full = x
        self._y_full = y
        self.plot.addItem(pg.ScatterPlotItem(x, y, pen=pg.mkPen(None), brush=pg.mkBrush('#1f77b4'), size=7))
        x0 = float(np.min(x))
        x1 = float(np.max(x))
        self.region = pg.LinearRegionItem(values=(x0, x1), orientation=pg.LinearRegionItem.Vertical, movable=True, brush=(120, 120, 120, 40))
        self.region.sigRegionChanged.connect(self._fit)
        self.plot.addItem(self.region)

    def _fit(self):
        if self._x_full is None or self._y_full is None:
            return
        x0, x1 = sorted(self.region.getRegion()) if self.region is not None else (float(np.min(self._x_full)), float(np.max(self._x_full)))
        mask = (self._x_full >= x0) & (self._x_full <= x1)
        x = self._x_full[mask]
        y = self._y_full[mask]
        if x.size < 3:
            self.coeff_label.setText(tr('Select a wider range for the fit.'))
            self._result = None
            return
        a = np.column_stack((x, x ** 2, x ** 3))
        coeffs, *_ = np.linalg.lstsq(a, y, rcond=None)
        self._result = tuple(float(v) for v in coeffs)
        self.range_label.setText(tr(f'Fit range: {x0:.4f} V .. {x1:.4f} V'))
        self.coeff_label.setText(', '.join(f'{v:.6g}' for v in self._result))
        self.plot.clearPlots()
        self.plot.addItem(pg.ScatterPlotItem(self._x_full, self._y_full, pen=pg.mkPen(None), brush=pg.mkBrush('#1f77b4'), size=7))
        x_fit = np.linspace(np.min(x), np.max(x), 400)
        y_fit = coeffs[0] * x_fit + coeffs[1] * (x_fit ** 2) + coeffs[2] * (x_fit ** 3)
        self.plot.plot(x_fit, y_fit, pen=pg.mkPen('#d62728', width=2))
        if self.region is not None and self.region.scene() is None:
            self.plot.addItem(self.region)

    def coefficients(self):
        return self._result


class TtplFitDialog(qt.QDialog):
    """Fits Ttpl = k1*(Utpl+offset) + k2*(Utpl+offset)^2 against Thtr in a selected range."""

    def __init__(self, parent, run_data, calibration):
        super().__init__(parent)
        self.run_data = run_data
        self.calibration = calibration
        self._result = None
        self._x_full = None
        self._y_full = None
        self.region = None
        self.setWindowTitle(tr('Thermopile fit'))
        self.resize(980, 720)
        self.setWindowModality(qt.Qt.WindowModal)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
        self._build_ui()
        self._prepare_data()
        self._fit()

    def _build_ui(self):
        root = qt.QVBoxLayout(self)
        info = qt.QLabel(tr('Select the usable range and fit Thtr as a quadratic function of shifted Utpl. The fit is updated immediately.'))
        info.setWordWrap(True)
        root.addWidget(info)
        self.plot = pg.PlotWidget(background='w')
        self.plot.setLabel('bottom', 'Utpl + offset', units='mV')
        self.plot.setLabel('left', 'Thtr', units='C')
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        root.addWidget(self.plot, 1)
        self.range_label = qt.QLabel('--')
        root.addWidget(self.range_label)
        self.coeff_label = qt.QLabel('--')
        self.coeff_label.setWordWrap(True)
        root.addWidget(self.coeff_label)
        buttons = qt.QHBoxLayout()
        buttons.addStretch(1)
        self.back_button = qt.QPushButton(tr('Back'))
        self.cancel_button = qt.QPushButton(tr('Cancel'))
        self.apply_button = qt.QPushButton(tr('Apply'))
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.apply_button)
        root.addLayout(buttons)
        self.back_button.clicked.connect(lambda: self.done(BACK_CODE))
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)

    def _prepare_data(self):
        x = np.asarray(self.run_data.get('UtplRaw', []), dtype=float) + float(getattr(self.calibration, 'utpl0', 0.0))
        y = np.asarray(self.run_data.get('Thtr', []), dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x = x[mask]
        y = y[mask]
        if x.size < 3:
            raise ValueError(tr('Not enough points to fit Ttpl(Utpl).'))
        self._x_full = x
        self._y_full = y
        self.plot.addItem(pg.ScatterPlotItem(x, y, pen=pg.mkPen(None), brush=pg.mkBrush('#1f77b4'), size=7))
        x0 = float(np.min(x))
        x1 = float(np.max(x))
        self.region = pg.LinearRegionItem(values=(x0, x1), orientation=pg.LinearRegionItem.Vertical, movable=True, brush=(120, 120, 120, 40))
        self.region.sigRegionChanged.connect(self._fit)
        self.plot.addItem(self.region)

    def _fit(self):
        if self._x_full is None or self._y_full is None:
            return
        x0, x1 = sorted(self.region.getRegion()) if self.region is not None else (float(np.min(self._x_full)), float(np.max(self._x_full)))
        mask = (self._x_full >= x0) & (self._x_full <= x1)
        x = self._x_full[mask]
        y = self._y_full[mask]
        if x.size < 3:
            self._result = None
            self.coeff_label.setText(tr('Select a wider range for the fit.'))
            return
        a = np.column_stack((x, x ** 2))
        coeffs, *_ = np.linalg.lstsq(a, y, rcond=None)
        self._result = tuple(float(v) for v in coeffs)
        self.range_label.setText(tr(f'Fit range: {x0:.4f} mV .. {x1:.4f} mV'))
        self.coeff_label.setText(f"Ttpl = {coeffs[0]:.6g}?U + {coeffs[1]:.6g}?U?")
        self.plot.clearPlots()
        self.plot.addItem(pg.ScatterPlotItem(self._x_full, self._y_full, pen=pg.mkPen(None), brush=pg.mkBrush('#1f77b4'), size=7))
        x_fit = np.linspace(np.min(x), np.max(x), 400)
        y_fit = coeffs[0] * x_fit + coeffs[1] * (x_fit ** 2)
        self.plot.plot(x_fit, y_fit, pen=pg.mkPen('#d62728', width=2))
        if self.region is not None and self.region.scene() is None:
            self.plot.addItem(self.region)

    def coefficients(self):
        return self._result


class CalibrationWizard:
    """Orchestrates the first stage of the calibration workflow."""

    def __init__(self, main_window):
        self.main = main_window

    def run(self):
        config = None
        references = None
        run1 = None
        selected = None
        run2 = None
        run3 = None
        stage = 'setup'

        while True:
            if stage == 'setup':
                setup = CalibrationSetupDialog(self.main, initial_config=config)
                if setup.exec() != qt.QDialog.Accepted:
                    return
                config = setup.get_config()
                references = [{'name': tr('Room'), 'temperature': float(config['room_temperature'])}] + list(config['calibrants'])
                self._apply_setup_to_calibration(config)
                stage = 'run1'
                continue

            if stage == 'run1':
                stage1 = CalibrationRunDialog(self.main, tr('Calibration stage 1: slow heating'), config, allow_back=True, run_mode='voltage', start_value=0.0, end_value=float(config['safe_voltage']), rate_per_min=float(config['rate_per_min']))
                result = stage1.exec()
                if result == BACK_CODE:
                    stage = 'setup'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                run1 = stage1.result_data()
                if not run1 or len(run1['amplitude']) == 0:
                    qt.QMessageBox.warning(self.main, tr('Calibration wizard'), tr('No slow-heating points were collected.'))
                    continue
                stage = 'cursor'
                continue

            if stage == 'cursor':
                cursors = CalibrationCursorDialog(self.main, run1, references, preset_points=selected)
                result = cursors.exec()
                if result == BACK_CODE:
                    stage = 'run1'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                selected = cursors.selected_points()
                stage = 'fit1'
                continue

            if stage == 'fit1':
                fit_dialog = CalibrationPolynomialDialog(self.main, selected)
                result = fit_dialog.exec()
                if result == BACK_CODE:
                    stage = 'cursor'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                coeffs = fit_dialog.coefficients()
                self._apply_thtr_coeffs(coeffs)
                stage = 'run2'
                continue

            if stage == 'run2':
                stage2 = CalibrationRunDialog(self.main, tr('Calibration stage 2: heater fit'), config, allow_back=True, run_mode='voltage', start_value=0.0, end_value=float(config['safe_voltage']), rate_per_min=float(config['rate_per_min']))
                result = stage2.exec()
                if result == BACK_CODE:
                    stage = 'fit1'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                run2 = stage2.result_data()
                if not run2 or len(run2['ao1_voltage']) == 0:
                    qt.QMessageBox.warning(self.main, tr('Calibration wizard'), tr('No heater-fit points were collected.'))
                    continue
                stage = 'heater_fit'
                continue

            if stage == 'heater_fit':
                heater_fit = HeaterFitDialog(self.main, run2)
                result = heater_fit.exec()
                if result == BACK_CODE:
                    stage = 'run2'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                self._apply_heater_coeffs(heater_fit.coefficients())
                stage = 'run3'
                continue

            if stage == 'run3':
                temp_max = float(self.main.calibration.theaterconv(float(config['safe_voltage'])))
                stage3 = CalibrationRunDialog(self.main, tr('Calibration stage 3: thermopile fit'), config, allow_back=True, run_mode='temperature', start_value=0.0, end_value=temp_max, rate_per_min=float(config.get('temp_rate_per_min', 15.0)))
                result = stage3.exec()
                if result == BACK_CODE:
                    stage = 'heater_fit'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                run3 = stage3.result_data()
                if not run3 or len(run3.get('UtplRaw', [])) == 0:
                    qt.QMessageBox.warning(self.main, tr('Calibration wizard'), tr('No thermopile-fit points were collected.'))
                    continue
                stage = 'ttpl_fit'
                continue

            if stage == 'ttpl_fit':
                ttpl_fit = TtplFitDialog(self.main, run3, self.main.calibration)
                result = ttpl_fit.exec()
                if result == BACK_CODE:
                    stage = 'run3'
                    continue
                if result != qt.QDialog.Accepted:
                    return
                self._apply_ttpl_coeffs(ttpl_fit.coefficients())
                qt.QMessageBox.information(self.main, tr('Calibration wizard'), tr('Calibration coefficients were applied.'))
                return

    def _apply_setup_to_calibration(self, config):
        default_json = Path(PROJECT_ROOT) / 'default_calibration.json'
        calib = Calibration()
        calib.read(str(default_json))
        calib.safe_voltage = float(config['safe_voltage'])
        calib.rhtr = float(config['r_inner'])
        calib.rghtr = float(config['r_guard'])
        calib._add_params()
        self.main.set_active_calibration(calib, path=str(default_json))

        gains = config['input_gains']
        self.main.ctrl.apply_input_gains(gains['ranges'], gains['auto_gain'], restart=True, emit_signal=True)
        if hasattr(self.main, 'inputGainsPanel'):
            self.main.inputGainsPanel.set_state(**gains)

    def _apply_thtr_coeffs(self, coeffs):
        calib = self.main.calibration
        thtr = coeffs['thtr']
        thtrd = coeffs['thtrd']
        calib.thtr0, calib.thtr1, calib.thtr2 = thtr
        calib.thtrd0, calib.thtrd1, calib.thtrd2 = thtrd
        calib._add_params()
        self.main.set_active_calibration(calib, path=self.main.calibPathInput.text().strip() or None)
        if hasattr(self.main, 'calib_window'):
            self.main.calib_window.update_calib_input_fields()

    def _apply_heater_coeffs(self, coeffs):
        calib = self.main.calibration
        calib.theater0, calib.theater1, calib.theater2 = coeffs
        calib._add_params()
        self.main.set_active_calibration(calib, path=self.main.calibPathInput.text().strip() or None)
        if hasattr(self.main, 'calib_window'):
            self.main.calib_window.update_calib_input_fields()

    def _apply_ttpl_coeffs(self, coeffs):
        calib = self.main.calibration
        if coeffs is None:
            return
        calib.ttpl0, calib.ttpl1 = coeffs
        calib._add_params()
        self.main.set_active_calibration(calib, path=self.main.calibPathInput.text().strip() or None)
        if hasattr(self.main, 'calib_window'):
            self.main.calib_window.update_calib_input_fields()
