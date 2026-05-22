from silx.gui import qt
from silx.gui.plot import PlotWindow
import numpy as np
from pioner_app.ui.localization import tr, apply_language


class _CompatRoi:
    def __init__(self):
        """Stub docstring."""
        self._min = 0.0
        self._max = 0.0

    def setMin(self, value):
        """Stub for `setMin`."""
        self._min = float(value)

    def setMax(self, value):
        """Stub for `setMax`."""
        self._max = float(value)

    def getRange(self):
        """Stub for `getRange`."""
        return self._min, self._max



class ResultsPlotOptionsDialog(qt.QDialog):

    def __init__(self, x_keys, mode_options, current_x, current_mode, segments, selected_ids, parent=None):
        """Stub docstring."""
        super().__init__(parent)
        self.setWindowTitle("Plot Options")
        self.setModal(True)
        self.setWindowModality(qt.Qt.WindowModal)
        self.resize(460, 460)

        layout = qt.QVBoxLayout(self)

        form = qt.QFormLayout()
        self.x_combo = qt.QComboBox()
        self.x_combo.addItems(x_keys)
        if current_x in x_keys:
            self.x_combo.setCurrentText(current_x)
        form.addRow("X axis", self.x_combo)

        self.mode_combo = qt.QComboBox()
        self.mode_combo.addItems(mode_options)
        if current_mode in mode_options:
            self.mode_combo.setCurrentText(current_mode)
        form.addRow("Plot mode", self.mode_combo)
        layout.addLayout(form)

        layout.addWidget(qt.QLabel("Profile segments"))
        self.segment_list = qt.QListWidget()
        self.segment_list.setSelectionMode(qt.QAbstractItemView.MultiSelection)
        layout.addWidget(self.segment_list, 1)

        for segment in segments:
            item = qt.QListWidgetItem(segment["label"])
            item.setData(qt.Qt.UserRole, segment["id"])
            item.setData(qt.Qt.UserRole + 1, segment.get("group", "other"))
            if segment["id"] in selected_ids:
                item.setSelected(True)
            self.segment_list.addItem(item)

        buttons_row = qt.QHBoxLayout()
        all_btn = qt.QPushButton("All")
        all_btn.clicked.connect(self._select_all)
        heating_btn = qt.QPushButton("Heating")
        heating_btn.clicked.connect(lambda: self._select_group("heating"))
        cooling_btn = qt.QPushButton("Cooling")
        cooling_btn.clicked.connect(lambda: self._select_group("cooling"))
        isotherm_btn = qt.QPushButton("Isotherm")
        isotherm_btn.clicked.connect(lambda: self._select_group("isotherm"))
        buttons_row.addWidget(all_btn)
        buttons_row.addWidget(heating_btn)
        buttons_row.addWidget(cooling_btn)
        buttons_row.addWidget(isotherm_btn)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

        footer_row = qt.QHBoxLayout()
        clear_all = qt.QPushButton("Clear")
        clear_all.clicked.connect(self.segment_list.clearSelection)
        footer_row.addWidget(clear_all)
        footer_row.addStretch()
        layout.addLayout(footer_row)

        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        apply_language(self)

    def _select_all(self):
        """Stub for `select_all`."""
        for row in range(self.segment_list.count()):
            self.segment_list.item(row).setSelected(True)

    def _select_group(self, group_name):
        """Stub for `select_group`."""
        self.segment_list.clearSelection()
        for row in range(self.segment_list.count()):
            item = self.segment_list.item(row)
            if item.data(qt.Qt.UserRole + 1) == group_name:
                item.setSelected(True)

    def selected_segment_ids(self):
        """Stub for `selected_segment_ids`."""
        return [item.data(qt.Qt.UserRole) for item in self.segment_list.selectedItems()]


class resultsDataWidget(qt.QWidget):

    MODE_OPTIONS = ["Multi Y", "X vs Y", "Overlay By Segment"]
    QUANTITY_LABELS = {
        "time(ms)": "Time (ms)",
        "temp": "Temperature (C)",
        "temp-hr": "Temperature HR (C)",
        "Uref": "Uref (DAQ)",
        "Ref": "Reference AO",
        "Ihtr": "Heater Current (mA)",
        "Thtr": "Heater Temperature (C)",
        "Taux": "Aux Temperature (C)",
    }

    def __init__(self, parent=None):
        """Stub docstring."""
        super().__init__(parent)

        self.processed_data = None
        self.sample_rate = None
        self.profile_segments = []
        self.segment_defs = []
        self.selected_segment_ids = []
        self.x_sources = {}
        self.y_sources = {}

        layout = qt.QVBoxLayout(self)

        toolbar = qt.QHBoxLayout()
        toolbar.addWidget(qt.QLabel("X:"))
        self.x_combo = qt.QComboBox()
        self.x_combo.currentIndexChanged.connect(self.update_plot)
        toolbar.addWidget(self.x_combo)

        toolbar.addWidget(qt.QLabel("Mode:"))
        self.mode_combo = qt.QComboBox()
        self.mode_combo.addItems(self.MODE_OPTIONS)
        self.mode_combo.currentIndexChanged.connect(self.update_plot)
        toolbar.addWidget(self.mode_combo)

        self.options_button = qt.QPushButton("Options")
        self.options_button.clicked.connect(self.open_plot_options)
        toolbar.addWidget(self.options_button)

        self.segment_info_label = qt.QLabel("Segments: full trace")
        toolbar.addWidget(self.segment_info_label)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        main_layout = qt.QHBoxLayout()
        self.y_list = qt.QListWidget()
        self.y_list.setSelectionMode(qt.QAbstractItemView.MultiSelection)
        self.y_list.itemSelectionChanged.connect(self.update_plot)
        main_layout.addWidget(self.y_list, 1)

        self.plot = PlotWindow(resetzoom=True)
        self.plot.setGraphGrid("major")
        main_layout.addWidget(self.plot, 4)
        layout.addLayout(main_layout)

        self.resultPlot = self.plot
        self.curveLegendsWidgetDock = None
        self.roiManager = None
        self.roi = _CompatRoi()
        self.curveColors = {
            "red": "red",
            "lightred": "#ff9999",
            "blue": "blue",
            "lightblue": "#99ccff",
            "gray": "gray",
        }
        apply_language(self)

    def clear(self):
        """Stub for `clear`."""
        self.plot.clear()

    def addCurve(self, *args, **kwargs):
        """Stub for `addCurve`."""
        return self.plot.addCurve(*args, **kwargs)

    def setRoi(self, x_min, x_max):
        """Stub for `setRoi`."""
        self.roi.setMin(x_min)
        self.roi.setMax(x_max)

    def removeRoi(self):
        """Stub for `removeRoi`."""
        self.roi = _CompatRoi()

    def _ensure_array(self, arr, length):
        """Stub for `ensure_array`."""
        if arr is None:
            return np.zeros(length)
        if np.isscalar(arr):
            return np.full(length, arr)

        arr = np.array(arr)
        if len(arr) > length:
            return arr[:length]
        if len(arr) < length:
            return np.pad(arr, (0, length - len(arr)), mode="edge")
        return arr

    def _quantity_label(self, key):
        """Stub for `quantity_label`."""
        return self.QUANTITY_LABELS.get(key, key)

    def _selected_y_keys(self, selected_items, x_key):
        """Stub for `selected_y_keys`."""
        keys = [item.text() for item in selected_items if item.text() != x_key]
        return keys or [item.text() for item in selected_items]

    def _multi_y_axis_label(self, y_keys):
        """Stub for `multi_y_axis_label`."""
        if not y_keys:
            return tr("Signals")
        if len(y_keys) == 1:
            return self._quantity_label(y_keys[0])
        return tr("Selected Quantities")

    def _segment_type_name(self, segment):
        """Stub for `segment_type_name`."""
        segment_type = str(getattr(segment, "type", "Segment"))
        if segment_type.startswith("VoltSine"):
            return tr("Sine")
        if "Isotherm" in segment_type:
            return tr("Isotherm")
        if "Ramp" in segment_type:
            return tr("Ramp")
        return segment_type

    def _segment_group(self, segment):
        """Stub for `segment_group`."""
        seg_type = self._segment_type_name(segment)
        if seg_type == "Isotherm":
            return "isotherm"
        if seg_type == "Sine":
            return "sine"
        if hasattr(segment, "slope"):
            slope = float(segment.slope())
            if slope > 0:
                return "heating"
            if slope < 0:
                return "cooling"
        return "other"

    def _segment_label(self, index, segment, duration_ms):
        """Stub for `segment_label`."""
        seg_type = self._segment_type_name(segment)
        group = self._segment_group(segment)
        suffix = ""
        if group == "heating":
            suffix = "Heating"
        elif group == "cooling":
            suffix = "Cooling"
        elif group == "isotherm":
            suffix = "Isotherm"
        elif group == "sine":
            suffix = "Sine"
        label_core = f"S{index} {seg_type}"
        if suffix and suffix != seg_type:
            label_core += f" {tr(suffix)}"
        return f"{label_core} ({duration_ms:.0f} ms)"

    def _build_segment_defs(self, total_length):
        """Stub for `build_segment_defs`."""
        self.segment_defs = []

        if not self.profile_segments or not self.sample_rate or total_length <= 0:
            self.selected_segment_ids = []
            self._update_segment_info_label()
            return

        cursor = 0
        for index, segment in enumerate(self.profile_segments, start=1):
            duration_ms = float(getattr(segment, "duration", 0) or 0)
            samples = max(1, int(round(duration_ms * self.sample_rate / 1000.0)))
            start = cursor
            stop = min(total_length, cursor + samples)
            if start >= total_length:
                break

            seg_type = self._segment_type_name(segment)
            seg_group = self._segment_group(segment)
            self.segment_defs.append({
                "id": index - 1,
                "label": self._segment_label(index, segment, duration_ms),
                "short_label": f"S{index} {seg_type}",
                "start": start,
                "stop": stop,
                "type": seg_type,
                "group": seg_group,
            })
            cursor += samples

        if cursor < total_length:
            self.segment_defs.append({
                "id": len(self.segment_defs),
                "label": f"Tail Residual ({total_length - cursor} samples)",
                "short_label": "Tail",
                "start": cursor,
                "stop": total_length,
                "type": "Tail",
                "group": "other",
            })

        self.selected_segment_ids = [segment["id"] for segment in self.segment_defs]
        self._update_segment_info_label()

    def _selected_segments(self):
        """Stub for `selected_segments`."""
        if not self.segment_defs or not self.selected_segment_ids:
            return []
        wanted = set(self.selected_segment_ids)
        return [segment for segment in self.segment_defs if segment["id"] in wanted]

    def _update_segment_info_label(self):
        """Stub for `update_segment_info_label`."""
        if not self.segment_defs:
            self.segment_info_label.setText(tr("Segments: full trace"))
            return
        selected_count = len(self._selected_segments())
        self.segment_info_label.setText(tr(f"Segments: {selected_count}/{len(self.segment_defs)}"))

    def _build_processed_sources(self):
        """Stub for `build_processed_sources`."""
        self.x_sources = {}
        self.y_sources = {}

        if self.processed_data is None:
            return

        keys = list(self.processed_data.keys())
        if not keys:
            return

        base = np.array(self.processed_data[keys[0]])
        if base is None or len(base) == 0:
            return

        for key in keys:
            arr = self._ensure_array(self.processed_data[key], len(base))
            self.x_sources[key] = arr
            self.y_sources[key] = arr

        self._build_segment_defs(len(base))

    def set_processed_data(self, data_dict, profile_segments=None, sample_rate=None):
        """Stub for `set_processed_data`."""
        self.clear()
        self.processed_data = data_dict
        self.profile_segments = list(profile_segments or [])
        self.sample_rate = sample_rate

        self._build_processed_sources()

        self.x_combo.blockSignals(True)
        self.x_combo.clear()
        self.x_combo.addItems(list(self.x_sources.keys()))
        if "Thtr" in self.x_sources:
            self.x_combo.setCurrentText("Thtr")
        self.x_combo.blockSignals(False)

        self.y_list.blockSignals(True)
        self.y_list.clear()
        for key in self.y_sources.keys():
            item = qt.QListWidgetItem(key)
            item.setSelected(key != self.x_combo.currentText())
            self.y_list.addItem(item)
        self.y_list.blockSignals(False)

        self._update_segment_info_label()
        self.update_plot()

    def open_plot_options(self):
        """Stub for `open_plot_options`."""
        dialog = ResultsPlotOptionsDialog(
            x_keys=list(self.x_sources.keys()),
            mode_options=self.MODE_OPTIONS,
            current_x=self.x_combo.currentText(),
            current_mode=self.mode_combo.currentText(),
            segments=self.segment_defs,
            selected_ids=self.selected_segment_ids,
            parent=self.window(),
        )
        apply_language(dialog)
        if dialog.exec_() != qt.QDialog.Accepted:
            return

        self.x_combo.setCurrentText(dialog.x_combo.currentText())
        self.mode_combo.setCurrentText(dialog.mode_combo.currentText())
        if self.segment_defs:
            selected = dialog.selected_segment_ids()
            self.selected_segment_ids = selected or [segment["id"] for segment in self.segment_defs]
        self._update_segment_info_label()
        self.update_plot()

    def _slice_for_segment(self, arr, segment):
        """Stub for `slice_for_segment`."""
        return arr[segment["start"]:segment["stop"]]

    def _default_segments(self, length):
        """Stub for `default_segments`."""
        return [{"id": -1, "label": "Full", "short_label": "Full", "start": 0, "stop": length, "type": "Full", "group": "other"}]

    def _plot_multi_y(self, x_key, x, selected_items, segments):
        """Stub for `plot_multi_y`."""
        y_keys = self._selected_y_keys(selected_items, x_key)
        self.plot.getXAxis().setLabel(self._quantity_label(x_key))
        self.plot.getYAxis().setLabel(self._multi_y_axis_label(y_keys))
        for key in y_keys:
            y = self.y_sources[key]
            for segment in segments:
                x_seg = self._slice_for_segment(x, segment)
                y_seg = self._slice_for_segment(y, segment)
                if len(x_seg) == 0 or len(y_seg) == 0:
                    continue
                legend_base = self._quantity_label(key)
                legend = legend_base if segment["id"] == -1 else f"{legend_base} | {segment['short_label']}"
                self.plot.addCurve(x_seg, y_seg, legend=legend)

    def _plot_x_vs_y(self, x_key, x, selected_items, segments):
        """Stub for `plot_x_vs_y`."""
        y_key = selected_items[0].text()
        if y_key == x_key and len(selected_items) > 1:
            y_key = selected_items[1].text()
        y = self.y_sources[y_key]
        self.plot.getXAxis().setLabel(self._quantity_label(x_key))
        self.plot.getYAxis().setLabel(self._quantity_label(y_key))
        for segment in segments:
            x_seg = self._slice_for_segment(x, segment)
            y_seg = self._slice_for_segment(y, segment)
            if len(x_seg) == 0 or len(y_seg) == 0:
                continue
            legend = f"{self._quantity_label(y_key)} vs {self._quantity_label(x_key)}" if segment["id"] == -1 else segment["short_label"]
            self.plot.addCurve(x_seg, y_seg, legend=legend, linestyle=" ", symbol="o")

    def _plot_overlay_by_segment(self, x_key, x, selected_items, segments):
        """Stub for `plot_overlay_by_segment`."""
        y_keys = self._selected_y_keys(selected_items, x_key)
        overlay_x_label = f"{self._quantity_label(x_key)} relative"
        self.plot.getXAxis().setLabel(overlay_x_label)
        self.plot.getYAxis().setLabel(self._multi_y_axis_label(y_keys))
        for key in y_keys:
            y = self.y_sources[key]
            for segment in segments:
                x_seg = self._slice_for_segment(x, segment)
                y_seg = self._slice_for_segment(y, segment)
                if len(x_seg) == 0 or len(y_seg) == 0:
                    continue
                x_local = x_seg - x_seg[0]
                legend = f"{self._quantity_label(key)} | {segment['short_label']}"
                self.plot.addCurve(x_local, y_seg, legend=legend)

    def update_plot(self):
        """Stub for `update_plot`."""
        self.plot.clear()

        if not self.x_sources or not self.y_sources:
            return

        x_key = self.x_combo.currentText()
        if x_key not in self.x_sources:
            return

        selected_items = self.y_list.selectedItems()
        if not selected_items:
            return

        x = self.x_sources[x_key]
        mode = self.mode_combo.currentText()
        segments = self._selected_segments() or self._default_segments(len(x))

        if mode == "Multi Y":
            self._plot_multi_y(x_key, x, selected_items, segments)
        elif mode == "X vs Y":
            self._plot_x_vs_y(x_key, x, selected_items, segments)
        else:
            self._plot_overlay_by_segment(x_key, x, selected_items, segments)

    def clear(self):
        """Stub for `clear`."""
        self.plot.clear()
        self.processed_data = None
        self.sample_rate = None
        self.profile_segments = []
        self.segment_defs = []
        self.selected_segment_ids = []
        self.x_sources = {}
        self.y_sources = {}
        self.y_list.clear()
        self.x_combo.clear()
        self.segment_info_label.setText("Segments: full trace")


