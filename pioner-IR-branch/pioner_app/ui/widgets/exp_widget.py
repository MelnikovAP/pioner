import copy
import json
import numpy as np

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QKeySequence
import pyqtgraph as pg
from pioner_app.core.settings import settings
from pioner_app.core.basemath import temperature_to_voltage, voltage_to_temperature
from pioner_app.core.calibration import Calibration


def _dialog_options():
    """?? ?? `dialog_options`."""
    options = QFileDialog.Options()
    options |= QFileDialog.DontUseNativeDialog
    return options


def _center_on_parent(widget):
    """?? ?? `center_on_parent`."""
    parent = widget.parentWidget()
    if parent is None:
        return
    widget.adjustSize()
    parent_rect = parent.frameGeometry()
    center = parent_rect.center()
    frame = widget.frameGeometry()
    frame.moveCenter(center)
    widget.move(frame.topLeft())


############################################
# CONVERSION
############################################

def volt_to_temperature(v, calibration=None):
    """?? ?? `volt_to_temperature`."""
    calibration = calibration or Calibration()
    v = voltage_to_temperature(v, calibration=calibration)
    return float(v) if np.ndim(v) == 0 else v


def temp_to_voltage(t, calibration=None):
    """?? ?? `temp_to_voltage`."""
    calibration = calibration or Calibration()
    t = temperature_to_voltage(t, calibration=calibration)
    return float(t) if np.ndim(t) == 0 else t


############################################
# SEGMENT MODEL
############################################

class Segment:

    def __init__(self, seg_type, duration_ms, start, end,
                 freq=0, ampl=0, offset=0):

        """?? ?? ? ?? ? ?."""
        self.type = seg_type
        self.duration = duration_ms
        self.start = start
        self.end = end

        self.freq = freq
        self.ampl = ampl
        self.offset = offset

    def slope(self):

        """?? ?? `slope`."""
        if self.duration == 0:
            return 0

        seconds = self.duration / 1000

        return (self.end - self.start) / seconds


############################################
# SEGMENT DIALOG
############################################

class SegmentDialog(QDialog):

    segment_changed = pyqtSignal()

    def __init__(self, unit, segment=None, parent=None):

        """creating of segment window dialog."""
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        if parent is not None:
            self.setParent(parent, Qt.Dialog)
            self.setWindowModality(Qt.WindowModal)
        
        self.unit = unit

        self.setWindowTitle("Segment")

        layout = QFormLayout()

        self.type = QComboBox()
        #self.type.addItems(["Ramp", "Isotherm", "Ramp Down"])
        self.type.addItems(["Ramp ↑", "Isotherm →", "Ramp down ↓","VoltSine ∿"])



        self.mode = QComboBox()
        self.mode.addItems(["Duration", "Rate"])

        self.duration = QDoubleSpinBox()
        self.duration.setRange(0, 1000000)
        self.duration.setSuffix(" ms")

        self.rate = QDoubleSpinBox()
        self.rate.setDecimals(3)
        self.rate.setRange(-1000000, 1000000)
        self.rate.setSuffix(f" {unit}/s")

        self.start = QDoubleSpinBox()
        self.start.setRange(-1000, 1000)
        self.start.setSuffix(unit)

        self.end = QDoubleSpinBox()
        self.end.setRange(-1000, 1000)
        self.end.setSuffix(unit)

        #sinemode
        self.frequency=QDoubleSpinBox()
        self.frequency.setSuffix("Hz")
     
        self.ampl=QDoubleSpinBox()
        self.ampl.setSuffix(unit)
     
        self.offset=QDoubleSpinBox()
        self.offset.setSuffix(unit)
      
        
        layout.addRow("Type", self.type)
        layout.addRow("Mode", self.mode)
        layout.addRow("Duration", self.duration)
        layout.addRow("Frequency", self.frequency)
        layout.addRow("Amplitude", self.ampl)
        layout.addRow("Offset", self.offset)

        layout.addRow("Rate", self.rate)
        layout.addRow("Start", self.start)
        layout.addRow("End", self.end)



        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)

        layout.addRow(ok)

        self.setLayout(layout)

        self.set_row_visible(self.offset, False)
        self.set_row_visible(self.ampl, False)
        self.set_row_visible(self.frequency, False)

        if segment:

            self.type.setCurrentText(segment.type)
            self.duration.setValue(segment.duration)
            self.start.setValue(segment.start)
            self.end.setValue(segment.end)

        self.mode.currentIndexChanged.connect(self.mode_changed)

        self.duration.valueChanged.connect(self.update_from_duration)
        self.rate.valueChanged.connect(self.update_from_rate)
        self.start.valueChanged.connect(self.update_from_duration)
        self.end.valueChanged.connect(self.update_from_duration)
        self.type.currentIndexChanged.connect(self.type_changed)
        self.duration.valueChanged.connect(self.emit_change)
        self.rate.valueChanged.connect(self.emit_change)
        self.start.valueChanged.connect(self.emit_change)
        self.end.valueChanged.connect(self.emit_change)
        self.frequency.valueChanged.connect(self.emit_change)
        self.ampl.valueChanged.connect(self.emit_change)
        self.offset.valueChanged.connect(self.emit_change)
        self.type.currentIndexChanged.connect(self.emit_change)
        self.mode_changed()

    def showEvent(self, event):
        """?? ?? `showEvent`."""
        super().showEvent(event)
        _center_on_parent(self)

    def emit_change(self):
        """?? ?? `emit_change`."""
        self.segment_changed.emit()


    def type_changed(self):

        """?? ?? `type_changed`."""
        if self.type.currentText() == "VoltSine ∿":

            self.set_row_visible(self.offset, True)
            self.set_row_visible(self.ampl, True)
            self.set_row_visible(self.frequency, True)

            self.set_row_visible(self.rate, False)
            self.set_row_visible(self.start, False)
            self.set_row_visible(self.end, False)

            self.duration.setEnabled(True)
            self.rate.setEnabled(False)
            self.mode.setCurrentIndex(0)
            self.mode.setEnabled(False)   #

        else:

            self.set_row_visible(self.offset, False)
            self.set_row_visible(self.ampl, False)
            self.set_row_visible(self.frequency, False)

            self.set_row_visible(self.rate, True)
            self.set_row_visible(self.start, True)
            self.set_row_visible(self.end, True)
            self.mode.setEnabled(True)
            self.mode_changed()
            

    def set_row_visible(self, widget, visible):

        """??? ?? `set_row_visible`."""
        layout = self.layout()

        for i in range(layout.rowCount()):

            label_item = layout.itemAt(i, QFormLayout.LabelRole)
            field_item = layout.itemAt(i, QFormLayout.FieldRole)

            if field_item and field_item.widget() == widget:

                if label_item:
                    label_item.widget().setVisible(visible)

                widget.setVisible(visible)
                return


    def mode_changed(self):

        """?? ?? `mode_changed`."""
        if self.mode.currentText() == "Duration":

            self.duration.setEnabled(True)
            self.rate.setEnabled(False)

        else:

            self.duration.setEnabled(False)
            self.rate.setEnabled(True)

    def update_from_duration(self):

        """? ?? `update_from_duration`."""
        if self.mode.currentText() != "Duration":
            return

        seconds = self.duration.value() / 1000

        if seconds == 0:
            return

        rate = (self.end.value() - self.start.value()) / seconds

        self.rate.blockSignals(True)
        self.rate.setValue(rate)
        self.rate.blockSignals(False)

    def update_from_rate(self):

        """? ?? `update_from_rate`."""
        if self.mode.currentText() != "Rate":
            return

        r = self.rate.value()

        if r == 0:
            return

        duration = abs(self.end.value() - self.start.value()) / abs(r)

        duration_ms = duration * 1000

        self.duration.blockSignals(True)
        self.duration.setValue(duration_ms)
        self.duration.blockSignals(False)

    def get_segment(self):

        """?? ?? `get_segment`."""
        return Segment(
            self.type.currentText(),
            self.duration.value(),
            self.start.value(),
            self.end.value(),
            self.frequency.value(),
            self.ampl.value(),
            self.offset.value()
        )


############################################
# PROFILE EDITOR WIDGET
############################################

class ProfileWidget(QWidget):

    profile_ready = pyqtSignal(object)
    result_ready = pyqtSignal(object)

    def __init__(self, parent=None):

            
        """?? ?? ? ?? ? ?."""
        super(ProfileWidget, self).__init__(parent=parent)
        
        self.segments = []
        self.mode = "voltage"
        self.segment_clipboard = []
        self.rate_labels = []
        self.rate_leaders = []
        self.segment_curves = []

        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        layout = QHBoxLayout(self)

        ###################################
        # LEFT PANEL
        ###################################

        left = QVBoxLayout()

        unit_box = QGroupBox("Units")

        unit_layout = QHBoxLayout()

        self.voltage_btn = QRadioButton("Voltage")
        self.temp_btn = QRadioButton("Temperature")

        self.voltage_btn.setChecked(True)

        self.voltage_btn.toggled.connect(self.unit_changed)

        unit_layout.addWidget(self.voltage_btn)
        unit_layout.addWidget(self.temp_btn)

        unit_box.setLayout(unit_layout)

        left.addWidget(unit_box)

        self.table = QTableWidget()

        self.table.setColumnCount(5)

        self.table.setHorizontalHeaderLabels(

            ["Type","Duration ms","Start","End","Rate"]

        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_segments_context_menu)
        self.table.cellDoubleClicked.connect(self.edit_segment)

        left.addWidget(self.table)
        self.hold_checkbox = QCheckBox("Hold final value")

        self.hold_value = QDoubleSpinBox()
        self.hold_value.setRange(-1000, 1000)

        left.addWidget(self.hold_checkbox)
        left.addWidget(self.hold_value)

        self.trigger_checkbox = QCheckBox("Analog trigger")

        self.trigger_level = QDoubleSpinBox()
        self.trigger_level.setRange(0, 10)
        self.trigger_level.setSuffix(" V")

        self.trigger_delay = QDoubleSpinBox()
        self.trigger_delay.setSuffix(" ms")

        left.addWidget(self.trigger_checkbox)
        left.addWidget(self.trigger_level)
        left.addWidget(self.trigger_delay)


        delete_btn = QPushButton("Delete Segment")
        delete_btn.clicked.connect(self.delete_segment)

        save_btn = QPushButton("Save Profile")
        save_btn.clicked.connect(self.save_profile)
        load_btn = QPushButton("Load Profile")
        load_btn.clicked.connect(self.load_profile)

        
        self.set_btn = QPushButton("SET")
        self.arm_btn = QPushButton("ARM")
        self.arm_btn.setEnabled(False)

        self.set_btn.clicked.connect(self.generate_profile)
        self.arm_btn.clicked.connect(self.arm_profile)

        left.addWidget(delete_btn)
        left.addWidget(save_btn)
        left.addWidget(load_btn)
        left.addWidget(self.set_btn)
        left.addWidget(self.arm_btn)

        layout.addLayout(left,1)



        ###################################
        # GRAPH
        ###################################

        self.plot = pg.PlotWidget()

        self.plot.setLabel("bottom","Time","s")
        self.plot.setLabel("left","Voltage","V")

        self.plot.showGrid(x=True,y=True)

        self.curve = self.plot.plot(pen=pg.mkPen('r', width=2))

        layout.addWidget(self.plot,3)

        self.plot.scene().sigMouseClicked.connect(self.add_segment)

        self.copy_shortcut = QShortcut(QKeySequence.Copy, self.table)
        self.copy_shortcut.activated.connect(self.copy_selected_segments)
        self.cut_shortcut = QShortcut(QKeySequence.Cut, self.table)
        self.cut_shortcut.activated.connect(self.cut_selected_segments)
        self.paste_shortcut = QShortcut(QKeySequence.Paste, self.table)
        self.paste_shortcut.activated.connect(self.paste_segments)
        self.delete_shortcut = QShortcut(QKeySequence.Delete, self.table)
        self.delete_shortcut.activated.connect(self.delete_segment)

    ###################################
    # SEGMENT CLIPBOARD
    ###################################

    def _selected_rows(self):

        """?? ?? `selected_rows`."""
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if rows:
            return sorted(rows)

        row = self.table.currentRow()
        return [row] if row >= 0 else []

    def _clone_segment(self, segment):

        """?? ?? `clone_segment`."""
        return copy.deepcopy(segment)

    def _set_current_row(self, row):

        """??? ?? `set_current_row`."""
        if 0 <= row < self.table.rowCount():
            self.table.setCurrentCell(row, 0)
            self.table.selectRow(row)

    def copy_selected_segments(self):

        """?? ?? `copy_selected_segments`."""
        rows = self._selected_rows()
        if not rows:
            return
        self.segment_clipboard = [self._clone_segment(self.segments[row]) for row in rows]

    def cut_selected_segments(self):

        """?? ?? `cut_selected_segments`."""
        rows = self._selected_rows()
        if not rows:
            return
        self.copy_selected_segments()
        for row in reversed(rows):
            self.segments.pop(row)
        self.refresh()
        self._set_current_row(min(rows[0], len(self.segments) - 1))

    def paste_segments(self):

        """? ?? `paste_segments`."""
        if not self.segment_clipboard:
            return

        rows = self._selected_rows()
        insert_at = rows[-1] + 1 if rows else len(self.segments)
        for offset, segment in enumerate(self.segment_clipboard):
            self.segments.insert(insert_at + offset, self._clone_segment(segment))

        self.refresh()
        if self.segment_clipboard:
            self.table.clearSelection()
            for offset in range(len(self.segment_clipboard)):
                row = insert_at + offset
                if row < self.table.rowCount():
                    self.table.selectRow(row)
            self._set_current_row(insert_at)

    def open_segments_context_menu(self, pos):

        """? ?? `open_segments_context_menu`."""
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        cut_action = menu.addAction("Cut")
        paste_action = menu.addAction("Paste")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        has_selection = bool(self._selected_rows())
        has_clipboard = bool(self.segment_clipboard)
        copy_action.setEnabled(has_selection)
        cut_action.setEnabled(has_selection)
        delete_action.setEnabled(has_selection)
        paste_action.setEnabled(has_clipboard)

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == copy_action:
            self.copy_selected_segments()
        elif action == cut_action:
            self.cut_selected_segments()
        elif action == paste_action:
            self.paste_segments()
        elif action == delete_action:
            self.delete_segment()

    ###################################
    # PUBLIC METHOD
    ###################################

    def get_profile(self):

        """?? ?? `get_profile`."""
        return getattr(self,"profile",None)

    def _get_active_calibration(self):

        """?? ?? `get_active_calibration`."""
        window = self.window()
        calibration = getattr(window, "calibration", None)
        return calibration or Calibration()

    def _convert_scalar(self, value, target_mode):

        """??? ?? `convert_scalar`."""
        calibration = self._get_active_calibration()
        if target_mode == "temperature":
            return float(volt_to_temperature(value, calibration=calibration))
        return float(temp_to_voltage(value, calibration=calibration))

    def _convert_sine_segment(self, segment, target_mode):

        """??? ?? `convert_sine_segment`."""
        low = segment.offset - segment.ampl
        high = segment.offset + segment.ampl

        low_conv = self._convert_scalar(low, target_mode)
        high_conv = self._convert_scalar(high, target_mode)

        segment.offset = (high_conv + low_conv) / 2.0
        segment.ampl = abs(high_conv - low_conv) / 2.0


    def _max_reachable_temperature(self):

        """Returns the maximum reachable temperature for the active calibration."""
        calibration = self._get_active_calibration()
        safe_voltage = float(max(getattr(calibration, "safe_voltage", 0.0), 0.0))
        return float(volt_to_temperature(np.array([safe_voltage]), calibration=calibration)[0])

    def _validate_temperature_segments(self):

        """Rejects temperature targets that would be clipped by the heater voltage limit."""
        if self.mode != "temperature":
            return True

        max_temp = self._max_reachable_temperature()
        violations = []

        for idx, segment in enumerate(self.segments, start=1):
            values = []
            seg_type = str(segment.type)

            if seg_type.startswith("VoltSine"):
                values.extend([segment.offset - segment.ampl, segment.offset + segment.ampl])
            elif "Isotherm" in seg_type:
                values.append(segment.start)
            else:
                values.extend([segment.start, segment.end])

            for value in values:
                if value < 0.0 or value > max_temp:
                    violations.append((idx, float(value)))

        if not violations:
            return True

        details = ", ".join([f"seg {idx}: {value:.2f} C" for idx, value in violations[:5]])
        if len(violations) > 5:
            details += ", ..."

        QMessageBox.critical(
            self,
            "Temperature Range Error",
            (
                f"Requested temperature exceeds the reachable range of 0..{max_temp:.2f} C for the current calibration.\n\n"
                "Out-of-range targets are clipped to the heater voltage limit and look like jumps.\n\n"
                f"Offending targets: {details}"
            ),
        )
        return False

    def _segment_values_in_voltage(self, segment):

        """?? ?? `segment_values_in_voltage`."""
        if self.mode == "voltage":
            if str(segment.type).startswith("VoltSine"):
                return {"amplitude": float(segment.ampl), "offset": float(segment.offset)}
            if "Isotherm" in str(segment.type):
                return {"value": float(segment.start)}
            return {"start": float(segment.start), "stop": float(segment.end)}

        if str(segment.type).startswith("VoltSine"):
            low_v = self._convert_scalar(segment.offset - segment.ampl, "voltage")
            high_v = self._convert_scalar(segment.offset + segment.ampl, "voltage")
            return {
                "offset": float((high_v + low_v) / 2.0),
                "amplitude": float(abs(high_v - low_v) / 2.0),
            }

        if "Isotherm" in str(segment.type):
            return {"value": float(self._convert_scalar(segment.start, "voltage"))}

        return {
            "start": float(self._convert_scalar(segment.start, "voltage")),
            "stop": float(self._convert_scalar(segment.end, "voltage")),
        }

    def _expand_ramp_for_execution(self, segment):

        """?? ?? `expand_ramp_for_execution`."""
        if self.mode == "voltage":
            values = self._segment_values_in_voltage(segment)
            return [{
                "type": "ramp",
                "duration": segment.duration,
                "start": values["start"],
                "stop": values["stop"],
            }]

        duration_ms = float(segment.duration)
        available_samples = max(2, int(round(duration_ms * settings.sample_rate / 1000.0)))
        span_parts = max(2, int(np.ceil(abs(float(segment.end) - float(segment.start)))))
        ms_parts = max(2, int(np.ceil(duration_ms)))
        parts = max(2, min(5000, available_samples, max(span_parts, ms_parts)))
        temp_points = np.linspace(segment.start, segment.end, parts + 1)
        voltage_points = [self._convert_scalar(value, "voltage") for value in temp_points]
        part_duration = duration_ms / parts

        steps = []
        for idx in range(parts):
            steps.append({
                "type": "ramp",
                "duration": part_duration,
                "start": float(voltage_points[idx]),
                "stop": float(voltage_points[idx + 1]),
            })
        return steps


    ###################################
    # SIGNAL EMIT
    ###################################

    def emit_profile(self):

        """?? ?? `emit_profile`."""
        if hasattr(self,"profile"):

            self.profile_ready.emit(self.profile)

    ###################################
    # UNIT CHANGE
    ###################################

    def unit_changed(self):

        """?? ?? `unit_changed`."""
        target_mode = "voltage" if self.voltage_btn.isChecked() else "temperature"
        if self.mode == target_mode:
            return

        for s in self.segments:
            if str(s.type).startswith("VoltSine"):
                self._convert_sine_segment(s, target_mode)
            else:
                s.start = self._convert_scalar(s.start, target_mode)
                s.end = self._convert_scalar(s.end, target_mode)

        self.hold_value.setValue(self._convert_scalar(self.hold_value.value(), target_mode))
        self.mode = target_mode

        if self.mode == "voltage":
            self.plot.setLabel("left", "Voltage", "V")
            self.hold_value.setSuffix(" V")
        else:
            self.plot.setLabel("left", "Temperature", "C")
            self.hold_value.setSuffix(" C")

        self.refresh()
        self.refresh_ui()

    ###################################
    # ADD SEGMENT
    ###################################

    def add_segment(self,event):

        """?? ?? `add_segment`."""
        unit = " V" if self.mode=="voltage" else " °C"

        dlg = SegmentDialog(unit, parent=self.window())

        dlg.segment_changed.connect(lambda: self.preview_segment(dlg))

        if dlg.exec_():

            self.segments.append(dlg.get_segment())

            self.refresh()

    ###################################
    # EDIT
    ###################################

    def edit_segment(self,row,col):

        """?? ?? `edit_segment`."""
        unit = " V" if self.mode=="voltage" else " В°C"

        seg = self.segments[row]

        dlg = SegmentDialog(unit, seg, parent=self.window())
        dlg.segment_changed.connect(self.refresh)
        if dlg.exec_():

            self.segments[row] = dlg.get_segment()

            self.refresh()

    ###################################
    # DELETE
    ###################################

    def delete_segment(self):

        """?? ?? `delete_segment`."""
        rows = self._selected_rows()

        if not rows:
            return

        for row in reversed(rows):
            self.segments.pop(row)

        self.refresh()
        self._set_current_row(min(rows[0], len(self.segments) - 1))

    ###################################
    # TABLE UPDATE
    ###################################

    def update_table(self):

        """? ?? `update_table`."""
        self.table.setRowCount(len(self.segments))
        type_map = {
            "Ramp ↑": "↑",
            "Isotherm →": "→",
            "Ramp down ↓": "↓",
            "VoltSine ∿": "∿"
        }

        
        for i,s in enumerate(self.segments):
            if s.type == "VoltSine ∿":
                slope = "-"
                self.table.setItem(i, 0, QTableWidgetItem(type_map.get(s.type, s.type)))
            
                self.table.setItem(i,1,QTableWidgetItem(str(s.duration)))
                self.table.setItem(i,2,QTableWidgetItem(str(s.freq)))
                self.table.setItem(i,3,QTableWidgetItem(str(s.ampl)))
                self.table.setItem(i,4,QTableWidgetItem(str(s.offset)))

            else:
                
                self.table.setItem(i, 0, QTableWidgetItem(type_map.get(s.type, s.type)))
                
                self.table.setItem(i,1,QTableWidgetItem(str(s.duration)))
                self.table.setItem(i,2,QTableWidgetItem(str(s.start)))
                self.table.setItem(i,3,QTableWidgetItem(str(s.end)))
                self.table.setItem(i,4,QTableWidgetItem(f"{s.slope():.2f}"))

    ###################################
    # GRAPH UPDATE
    ###################################
    def refresh_ui(self):
        """? ?? `refresh_ui`."""
        self.update_table()

    def _clear_rate_labels(self):

        """? ?? `clear_rate_labels`."""
        for label in self.rate_labels:
            self.plot.removeItem(label)
        for leader in self.rate_leaders:
            self.plot.removeItem(leader)
        self.rate_labels = []
        self.rate_leaders = []

    def _clear_segment_curves(self):

        """? ?? `clear_segment_curves`."""
        for curve in self.segment_curves:
            self.plot.removeItem(curve)
        self.segment_curves = []

    def _segment_color(self, segment):

        """?? ?? `segment_color`."""
        segment_type = str(segment.type)
        if segment_type.startswith("VoltSine"):
            return (120, 120, 120)
        if "Isotherm" in segment_type:
            return (40, 150, 70)
        rate = segment.slope()
        if rate > 0:
            return (200, 40, 40)
        if rate < 0:
            return (40, 90, 210)
        return (40, 150, 70)

    def _rate_unit_label(self):

        """?? ?? `rate_unit_label`."""
        return "C/s" if self.mode == "temperature" else "V/s"

    def _rate_color(self, rate):

        """?? ?? `rate_color`."""
        if rate > 0:
            return (200, 40, 40)
        if rate < 0:
            return (40, 90, 210)
        return (40, 150, 70)

    def _add_rate_labels(self):

        """?? ?? `add_rate_labels`."""
        self._clear_rate_labels()
        vb = self.plot.getPlotItem().vb
        time_cursor = 0.0

        for segment in self.segments:
            duration = segment.duration / 1000.0
            start_time = time_cursor
            end_time = time_cursor + duration
            time_cursor = end_time

            if duration <= 0:
                continue
            if str(segment.type).startswith("VoltSine") or "Isotherm" in str(segment.type):
                continue

            rate = segment.slope()
            if abs(rate) < 1e-12:
                continue

            mid_x = (start_time + end_time) / 2.0
            mid_y = (segment.start + segment.end) / 2.0
            x_span, y_span = vb.viewRange()
            dx = max((x_span[1] - x_span[0]) * 0.03, duration * 0.08, 0.12)
            dy = max((y_span[1] - y_span[0]) * 0.04, abs(segment.end - segment.start) * 0.12, 0.12)
            label_x = mid_x + dx
            label_y = mid_y + (dy if rate >= 0 else -dy)

            leader = self.plot.plot(
                [mid_x, label_x],
                [mid_y, label_y],
                pen=pg.mkPen(self._rate_color(rate), width=1.5, style=Qt.DashLine),
            )
            self.rate_leaders.append(leader)

            label = pg.TextItem(
                text=f"{rate:+.2f} {self._rate_unit_label()}",
                color=self._rate_color(rate),
                anchor=(0, 0.5),
            )
            label.setPos(label_x, label_y)
            self.plot.addItem(label)
            self.rate_labels.append(label)

    def update_plot(self):

        """? ?? `update_plot`."""
        self._clear_segment_curves()
        self._clear_rate_labels()
        self.curve.setData([], [])

        time = 0.0
        preview_rate = 20000

        for s in self.segments:

            duration = s.duration / 1000.0
            samples = max(2, int(preview_rate * duration))
            dt = 1.0 / preview_rate

            if str(s.type).startswith("VoltSine"):
                local_t = np.arange(samples) * dt
                local_v = s.offset + s.ampl * np.sin(2 * np.pi * s.freq * local_t)
            else:
                local_t = np.linspace(0, duration, samples)
                local_v = np.linspace(s.start, s.end, samples)

            x = time + local_t
            curve = self.plot.plot(x, local_v, pen=pg.mkPen(self._segment_color(s), width=3))
            self.segment_curves.append(curve)
            time += duration

        self._add_rate_labels()

    ###################################
    # GENERATE PROFILE
    ###################################

    def generate_profile(self):

        """profile generation procedure `generate_profile`."""
        rate = settings.sample_rate

        ch1 = []  # creating of channel list
        total_samples = 0

        for s in self.segments:

            samples = int(rate * (s.duration / 1000))
            total_samples += samples

            if s.type == "Isotherm →":
                seg = np.ones(samples) * s.start

            elif s.type == "VoltSine ∿":
                t = np.linspace(0, s.duration/1000, samples)
                seg = s.offset + s.ampl * np.sin(2*np.pi*s.freq*t)

            else:
                seg = np.linspace(s.start, s.end, samples)

            ch1.extend(seg)

        ch1 = np.array(ch1)
        calibration = self._get_active_calibration()

        # temp to voltage
        if self.mode == "temperature":
            ch1 = temperature_to_voltage(ch1, calibration=calibration)

        # filling zeros
        ch0 = np.zeros_like(ch1)

        # filling zeros
        ch2 = np.zeros_like(ch1)

        if self.trigger_checkbox.isChecked():

            delay_samples = int(rate * (self.trigger_delay.value()/1000))

            if delay_samples < len(ch2):

                ch2[:delay_samples] = 0
                ch2[delay_samples:delay_samples+int(0.05*rate)] = self.trigger_level.value()

        # HOLD
        if self.hold_checkbox.isChecked():

            hold_val = self.hold_value.value()

            if self.mode == "temperature":
                hold_val = temperature_to_voltage(hold_val, calibration=calibration)

        data = []
        t=0
        for s in self.segments:

            if s.type == "Isotherm →":

                data.append({
                    "type": "isotherm",
                    "duration": s.duration,   # in ms
                    "value": s.start
                })
                t=t+s.duration
            elif s.type in ["Ramp ↑", "Ramp down ↓"]:

                data.append({
                    "type": "ramp",
                    "duration": s.duration,
                    "start": s.start,
                    "stop": s.end
                })
                t=t+s.duration
            elif s.type == "VoltSine ∿":

                data.append({
                    "type": "sine",
                    "duration": s.duration,
                    "frequency": s.freq,
                    "amplitude": s.ampl,
                    "offset": s.offset
                })
                t=t+s.duration
        profile_dict = {
            "channels": {
                "0":[{"type": "isotherm",
                    "duration": t,   # in ms
                    "value": s.start}],
                "1": data
                #"2": data2
            }
        }
        with open("generated_profile.json", "w") as f:
            json.dump(profile_dict, f, indent=4)

        self.profile = profile_dict

        print("JSON created")
        self.arm_btn.setEnabled(True)
        self.emit_profile()
        return profile_dict

    def preview_segment(self, dlg):

        """?? ?? `preview_segment`."""
        s = dlg.get_segment()

        temp_segments = list(self.segments)

        t = []
        v = []

        time = 0

        for seg in temp_segments:

            duration = seg.duration / 1000

            if seg.type == "VoltSine ∿":

                local_t = np.linspace(0, duration, 200)
                local_v = seg.offset + seg.ampl * np.sin(2*np.pi*seg.freq*local_t)

                t.extend(time + local_t)
                v.extend(local_v)

            else:

                t.append(time)
                v.append(seg.start)

                time += duration

                t.append(time)
                v.append(seg.end)

                continue

            time += duration

        self.curve.setData(t, v)

    ###################################
    # SAVE
    ###################################

    def save_profile(self):

        """? ?? `save_profile`."""
        data = []
        t=0
        for s in self.segments:

            if s.type == "Isotherm →":

                data.append({
                    "type": "isotherm",
                    "duration": s.duration,   # in ms
                    "value": s.start
                })
                t=t+s.duration
            elif s.type in ["Ramp ↑", "Ramp down ↓"]:

                data.append({
                    "type": "ramp",
                    "duration": s.duration,
                    "start": s.start,
                    "stop": s.end
                })
                t=t+s.duration
            elif s.type == "VoltSine ∿":

                data.append({
                    "type": "sine",
                    "duration": s.duration,
                    "frequency": s.freq,
                    "amplitude": s.ampl,
                    "offset": s.offset
                })
                t=t+s.duration
        profile = {
            "channels": {
                "0":[{"type": "isotherm",
                    "duration": t,   # in ms
                    "value": s.start}],
                "1": data
                #"2": data2
            }
        }

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Profile", "profile.json", "JSON (*.json)", options=_dialog_options()
        )

        if not path:
            return

        with open(path, "w") as f:
            json.dump(profile, f, indent=4)

        print("Profile saved")
    
    ###################################
    #LOAD
    ###################################
    def load_profile(self):

        """? ?? `load_profile`."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Profile", "", "JSON (*.json)", options=_dialog_options()
        )

        if not path:
            return

        with open(path, "r") as f:
            profile = json.load(f)

        self.segments.clear()

        ################################
        # РїСЂРѕРІРµСЂРєР° СЃС‚СЂСѓРєС‚СѓСЂС‹
        ################################

        if "channels" not in profile:
            print("Wrong format")
            return

        channels = profile["channels"]

        if "1" not in channels:
            print("Channel 1 not found")
            return

        data = channels["1"]

        ################################
        # Р·Р°РіСЂСѓР·РєР° СЃРµРіРјРµРЅС‚РѕРІ
        ################################

        for s in data:

            seg_type = s.get("type")

            if seg_type == "isotherm":

                seg = Segment(
                    "Isotherm →",
                    s["duration"],
                    s["value"],
                    s["value"]
                )

            elif seg_type == "ramp":

                seg = Segment(
                    "Ramp ↑",   # РЅР°РїСЂР°РІР»РµРЅРёРµ РЅРµ РІР°Р¶РЅРѕ
                    s["duration"],
                    s["start"],
                    s["stop"]
                )

            elif seg_type == "sine":

                seg = Segment(
                    "VoltSine ∿",
                    s["duration"],
                    0, 0,
                    s["frequency"],
                    s["amplitude"],
                    s["offset"]
                )

            else:
                continue

            self.segments.append(seg)



        print(f"Loaded {len(self.segments)} segments")

        self.refresh()


    def build_profile_for_experiment(self):

        """?? ?? `build_profile_for_experiment`."""
        data = []
        total_time = 0

        for s in self.segments:

            if "Isotherm" in str(s.type):

                value = self._segment_values_in_voltage(s)["value"]
                data.append({
                    "type": "isotherm",
                    "duration": s.duration,
                    "value": value
                })

            elif "Ramp" in str(s.type):

                ramp_steps = self._expand_ramp_for_execution(s)
                data.extend(ramp_steps)

            elif str(s.type).startswith("VoltSine"):

                values = self._segment_values_in_voltage(s)
                data.append({
                    "type": "sine",
                    "duration": s.duration,
                    "frequency": s.freq,
                    "amplitude": values["amplitude"],
                    "offset": values["offset"]
                })

            total_time += s.duration

        ch0 = [{
            "type": "isotherm",
            "duration": total_time,
            "value": 0.1
        }]

        ch1 = data

        ch2 = [{
            "type": "isotherm",
            "duration": total_time,
            "value": 0
        }]

        profile = {
            "channels": {
                "0": ch0,
                "1": ch1,
                "2": ch2
            }
        }

        return profile


    def arm_profile(self):
        
        """?? ?? `arm_profile`."""
        from pioner_app.hardware.daq_controller import get_daq_controller
        ctrl = get_daq_controller()

        if not ctrl.em:
            print("DAQ not connected")
            return

        if not self.segments:
            print("No segments")
            return

        if not self._validate_temperature_segments():
            return

        profile = self.build_profile_for_experiment()

        from threading import Thread

        def worker():
            """?? ?? `worker`."""
            try:
                # вњ… РїРµСЂРµРґР°С‘Рј dict РЅР°РїСЂСЏРјСѓСЋ
                data = ctrl.run_fast_heat_profile(profile)

                print("Experiment finished")

                self.result_ready.emit(data)

            except Exception as e:
                print(f"Fast heat error: {e}")

        Thread(target=worker, daemon=True).start()
    


    ###################################
    # REFRESH
    ###################################

    def refresh(self):

        """? ?? `refresh`."""
        self.update_table()
        self.update_plot()







