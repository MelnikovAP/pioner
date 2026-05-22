import json
from pathlib import Path

import h5py
import numpy as np
from silx.gui import qt
from PyQt5.QtCore import QEvent
from silx.gui.plot import PlotWindow
from pioner_app.ui.localization import tr, apply_language


def _dialog_options():
    options = qt.QFileDialog.Options()
    options |= qt.QFileDialog.DontUseNativeDialog
    return options


class SimpleProcessWidget(qt.QWidget):
    SEGMENT_OPTIONS = ["Full trace", "Heating", "Cooling", "Isotherm"]
    FIT_OPTIONS = ["Linear", "Quadratic", "Cubic", "Quartic", "Exponential", "Logarithmic", "Power"]
    LEFT_MARKER = "range start"
    RIGHT_MARKER = "range end"
    EXCLUDE_LEFT_MARKER = "exclude start"
    EXCLUDE_RIGHT_MARKER = "exclude end"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_path = ""
        self.data_dict = {}
        self.current_x = None
        self.current_y = None
        self.original_y = None
        self.processed_y = None
        self.fit_y = None
        self.range_min = None
        self.range_max = None
        self.exclude_min = None
        self.exclude_max = None
        self._pending_marker = "min"
        self._drag_start_x = None
        self._drag_mode = None
        self._last_curve_key = None
        self._build_ui()
        self._install_plot_click_filter()
        self._connect()
        self._arm_start_marker(initial=True)
        apply_language(self)

    def _build_ui(self):
        root = qt.QHBoxLayout(self)

        left = qt.QVBoxLayout()
        root.addLayout(left, 0)

        file_group = qt.QGroupBox("Data source")
        file_layout = qt.QVBoxLayout(file_group)
        file_row = qt.QHBoxLayout()
        self.filePathInput = qt.QLineEdit()
        self.fileBrowseButton = qt.QToolButton()
        self.fileBrowseButton.setText("...")
        file_row.addWidget(self.filePathInput, 1)
        file_row.addWidget(self.fileBrowseButton, 0)
        file_layout.addLayout(file_row)
        self.loadFileButton = qt.QPushButton("Open h5")
        file_layout.addWidget(self.loadFileButton)
        left.addWidget(file_group)

        select_group = qt.QGroupBox("Selection")
        select_layout = qt.QFormLayout(select_group)
        self.xAxisCombo = qt.QComboBox()
        self.curveCombo = qt.QComboBox()
        self.segmentCombo = qt.QComboBox()
        self.segmentCombo.addItems(self.SEGMENT_OPTIONS)
        select_layout.addRow("X axis", self.xAxisCombo)
        select_layout.addRow("Curve", self.curveCombo)
        select_layout.addRow("Segment", self.segmentCombo)
        left.addWidget(select_group)

        range_group = qt.QGroupBox("Selected range")
        range_layout = qt.QFormLayout(range_group)
        self.rangeMinLabel = qt.QLabel("---")
        self.rangeMaxLabel = qt.QLabel("---")
        self.rangeHintLabel = qt.QLabel("Left drag selects fit range. Ctrl + left drag selects an excluded part for the fit.")
        self.rangeHintLabel.setWordWrap(True)
        self.setStartButton = qt.QPushButton("Set start")
        self.setStartButton.setCheckable(True)
        self.setEndButton = qt.QPushButton("Set end")
        self.setEndButton.setCheckable(True)
        self.excludeMinLabel = qt.QLabel("---")
        self.excludeMaxLabel = qt.QLabel("---")
        self.clearRangeButton = qt.QPushButton("Clear range")
        self.clearExcludeButton = qt.QPushButton("Clear exclude")
        marker_buttons = qt.QHBoxLayout()
        marker_buttons.addWidget(self.setStartButton)
        marker_buttons.addWidget(self.setEndButton)
        range_layout.addRow("X min", self.rangeMinLabel)
        range_layout.addRow("X max", self.rangeMaxLabel)
        range_layout.addRow("Exclude min", self.excludeMinLabel)
        range_layout.addRow("Exclude max", self.excludeMaxLabel)
        range_layout.addRow(marker_buttons)
        range_layout.addRow(self.clearRangeButton)
        range_layout.addRow(self.clearExcludeButton)
        range_layout.addRow(self.rangeHintLabel)
        left.addWidget(range_group)

        fit_group = qt.QGroupBox("Math operations")
        fit_layout = qt.QVBoxLayout(fit_group)
        fit_form = qt.QFormLayout()
        self.fitTypeCombo = qt.QComboBox()
        self.fitTypeCombo.addItems(self.FIT_OPTIONS)
        fit_form.addRow("Fit type", self.fitTypeCombo)
        fit_layout.addLayout(fit_form)
        fit_buttons = qt.QHBoxLayout()
        self.fitButton = qt.QPushButton("Fit range")
        self.subtractFitButton = qt.QPushButton("Subtract fit")
        fit_buttons.addWidget(self.fitButton)
        fit_buttons.addWidget(self.subtractFitButton)
        fit_layout.addLayout(fit_buttons)
        self.resetProcessedButton = qt.QPushButton("Reset curve")
        fit_layout.addWidget(self.resetProcessedButton)
        left.addWidget(fit_group)

        io_group = qt.QGroupBox("Processing")
        io_layout = qt.QHBoxLayout(io_group)
        self.saveProcessingButton = qt.QPushButton("Save processing")
        self.openProcessingButton = qt.QPushButton("Open processing")
        io_layout.addWidget(self.saveProcessingButton)
        io_layout.addWidget(self.openProcessingButton)
        left.addWidget(io_group)
        left.addStretch(1)

        right = qt.QVBoxLayout()
        root.addLayout(right, 1)
        self.plot = PlotWindow(resetzoom=True)
        self.plot.setGraphGrid("major")
        self.plot.getXAxis().setLabel("X")
        self.plot.getYAxis().setLabel("Y")
        self.plot.setActiveCurveHandling(False)
        right.addWidget(self.plot, 1)
        self.statusLabel = qt.QLabel("Load an h5 file to begin.")
        right.addWidget(self.statusLabel)

    def _connect(self):
        self.fileBrowseButton.clicked.connect(self.browse_file)
        self.loadFileButton.clicked.connect(self.load_selected_file)
        self.xAxisCombo.currentTextChanged.connect(self.refresh_view)
        self.curveCombo.currentTextChanged.connect(self.refresh_view)
        self.segmentCombo.currentTextChanged.connect(self.refresh_view)
        self.fitButton.clicked.connect(self.fit_selected_range)
        self.subtractFitButton.clicked.connect(self.subtract_fit_from_curve)
        self.resetProcessedButton.clicked.connect(self.reset_processed_curve)
        self.saveProcessingButton.clicked.connect(self.save_processing)
        self.openProcessingButton.clicked.connect(self.open_processing)
        self.setStartButton.clicked.connect(lambda: self._arm_start_marker())
        self.setEndButton.clicked.connect(lambda: self._arm_end_marker())
        self.clearRangeButton.clicked.connect(self._clear_range)
        self.clearExcludeButton.clicked.connect(self._clear_exclude_range)
        self.plot.sigPlotSignal.connect(self.handle_plot_signal)

    def _install_plot_click_filter(self):
        backend = None
        try:
            backend = self.plot.getWidgetHandle()
        except Exception:
            backend = None
        if backend is not None:
            backend.installEventFilter(self)

    def _pixel_to_x(self, event):
        pos = event.position() if hasattr(event, 'position') else event.pos()
        xpix = float(pos.x())
        ypix = float(pos.y())
        data_pos = self.plot.pixelToData(xpix, ypix)
        if data_pos is None or len(data_pos) < 1:
            return None
        return float(data_pos[0])

    def _set_range_from_drag(self, start_x, end_x):
        left = float(min(start_x, end_x))
        right = float(max(start_x, end_x))
        self.range_min = left
        self.range_max = right
        self.rangeMinLabel.setText(f"{left:.6g}")
        self.rangeMaxLabel.setText(f"{right:.6g}")
        self.statusLabel.setText(tr("Fit range selected."))
        self.refresh_view()

    def _set_exclude_from_drag(self, start_x, end_x):
        left = float(min(start_x, end_x))
        right = float(max(start_x, end_x))
        self.exclude_min = left
        self.exclude_max = right
        self.excludeMinLabel.setText(f"{left:.6g}")
        self.excludeMaxLabel.setText(f"{right:.6g}")
        self.statusLabel.setText(tr("Excluded fit range selected."))
        self.refresh_view()

    def eventFilter(self, obj, event):
        if obj is not None:
            if event.type() == QEvent.MouseButtonPress:
                try:
                    button = event.button()
                except Exception:
                    button = None
                if button == qt.Qt.LeftButton:
                    x_value = self._pixel_to_x(event)
                    if x_value is not None:
                        self._drag_start_x = x_value
                        modifiers = event.modifiers() if hasattr(event, 'modifiers') else qt.Qt.NoModifier
                        self._drag_mode = 'exclude' if modifiers & qt.Qt.ControlModifier else 'range'
                        return True
            elif event.type() == QEvent.MouseButtonRelease:
                try:
                    button = event.button()
                except Exception:
                    button = None
                if button == qt.Qt.LeftButton and self._drag_start_x is not None:
                    x_value = self._pixel_to_x(event)
                    if x_value is not None:
                        if abs(x_value - self._drag_start_x) > 1e-12:
                            if self._drag_mode == 'exclude':
                                self._set_exclude_from_drag(self._drag_start_x, x_value)
                            else:
                                self._set_range_from_drag(self._drag_start_x, x_value)
                        else:
                            self._set_marker_from_x(float(x_value))
                    self._drag_start_x = None
                    self._drag_mode = None
                    return True
        return super().eventFilter(obj, event)

    def _set_marker_from_x(self, x_value):
        if self._pending_marker == "max":
            self.range_max = float(x_value)
            self.rangeMaxLabel.setText(f"{self.range_max:.6g}")
            self._arm_start_marker(initial=True)
            self.statusLabel.setText(tr("End marker placed."))
        else:
            self.range_min = float(x_value)
            self.rangeMinLabel.setText(f"{self.range_min:.6g}")
            self.setStartButton.setChecked(False)
            self.statusLabel.setText(tr("Start marker placed. Press Set end to place the end marker."))
        self.refresh_view()

    def _arm_start_marker(self, initial=False):
        self._pending_marker = "min"
        self.setStartButton.setChecked(True)
        self.setEndButton.setChecked(False)
        if not initial:
            self.statusLabel.setText(tr("Left click on the graph to place the start marker."))

    def _arm_end_marker(self):
        self._pending_marker = "max"
        self.setStartButton.setChecked(False)
        self.setEndButton.setChecked(True)
        self.statusLabel.setText(tr("Left click on the graph to place the end marker."))

    def _clear_range(self):
        self.range_min = None
        self.range_max = None
        self.fit_y = None
        self.rangeMinLabel.setText("---")
        self.rangeMaxLabel.setText("---")
        self._arm_start_marker()
        self.refresh_view()
        self.statusLabel.setText(tr("Range markers cleared."))

    def _clear_exclude_range(self):
        self.exclude_min = None
        self.exclude_max = None
        self.fit_y = None
        self.excludeMinLabel.setText("---")
        self.excludeMaxLabel.setText("---")
        self.refresh_view()
        self.statusLabel.setText(tr("Excluded range cleared."))

    def browse_file(self):
        path, _ = qt.QFileDialog.getOpenFileName(self, tr("Open h5"), "", "HDF5 files (*.h5)", options=_dialog_options())
        if path:
            self.filePathInput.setText(path)

    def _read_h5_dict(self, path):
        result = {}
        with h5py.File(path, "r") as h5:
            group = h5["data"] if "data" in h5 else h5
            for key, item in group.items():
                if hasattr(item, "shape"):
                    try:
                        result[key] = np.asarray(item)
                    except Exception:
                        pass
        return result

    def load_selected_file(self):
        path = self.filePathInput.text().strip()
        if not path:
            self.statusLabel.setText(tr("Select an h5 file first."))
            return
        self.source_path = path
        self.data_dict = self._read_h5_dict(path)
        keys = sorted(self.data_dict.keys())
        self.xAxisCombo.blockSignals(True)
        self.curveCombo.blockSignals(True)
        self.xAxisCombo.clear()
        self.curveCombo.clear()
        self.xAxisCombo.addItems(keys)
        self.curveCombo.addItems(keys)
        if "time" in self.data_dict:
            self.xAxisCombo.setCurrentText("time")
        elif "time(s)" in self.data_dict:
            self.xAxisCombo.setCurrentText("time(s)")
        elif "time(ms)" in self.data_dict:
            self.xAxisCombo.setCurrentText("time(ms)")
        if "temp" in self.data_dict:
            self.curveCombo.setCurrentText("temp")
        self.xAxisCombo.blockSignals(False)
        self.curveCombo.blockSignals(False)
        self.range_min = None
        self.range_max = None
        self.exclude_min = None
        self.exclude_max = None
        self.original_y = None
        self.processed_y = None
        self.fit_y = None
        self.rangeMinLabel.setText("---")
        self.rangeMaxLabel.setText("---")
        self.excludeMinLabel.setText("---")
        self.excludeMaxLabel.setText("---")
        self._arm_start_marker(initial=True)
        self.refresh_view()
        self.statusLabel.setText(tr(f"Loaded {Path(path).name}"))

    def _segment_mask(self, x, y):
        mode = self.segmentCombo.currentText()
        if mode == "Full trace" or len(x) < 3:
            return np.ones(len(x), dtype=bool)
        slope = np.gradient(y, x)
        finite = np.isfinite(slope)
        if not np.any(finite):
            return np.ones(len(x), dtype=bool)
        ref = np.nanmax(np.abs(slope[finite]))
        tol = max(ref * 0.05, 1e-9)
        if mode == "Heating":
            return slope > tol
        if mode == "Cooling":
            return slope < -tol
        return np.abs(slope) <= tol

    def _current_arrays(self):
        x_key = self.xAxisCombo.currentText()
        y_key = self.curveCombo.currentText()
        if not x_key or not y_key or x_key not in self.data_dict or y_key not in self.data_dict:
            return None, None
        x = np.asarray(self.data_dict[x_key], dtype=float)
        y = np.asarray(self.data_dict[y_key], dtype=float)
        n = min(len(x), len(y))
        return x[:n], y[:n]

    def _selected_range_mask(self, x, base_mask):
        mask = np.array(base_mask, copy=True)
        if self.range_min is not None:
            right = self.range_max if self.range_max is not None else self.range_min
            mask &= x >= min(self.range_min, right)
        if self.range_max is not None:
            left = self.range_min if self.range_min is not None else self.range_max
            mask &= x <= max(left, self.range_max)
        if self.exclude_min is not None and self.exclude_max is not None:
            exclude_left = min(self.exclude_min, self.exclude_max)
            exclude_right = max(self.exclude_min, self.exclude_max)
            mask &= ((x < exclude_left) | (x > exclude_right))
        return mask

    def _selected_apply_mask(self, x, base_mask):
        mask = np.array(base_mask, copy=True)
        if self.range_min is not None:
            right = self.range_max if self.range_max is not None else self.range_min
            mask &= x >= min(self.range_min, right)
        if self.range_max is not None:
            left = self.range_min if self.range_min is not None else self.range_max
            mask &= x <= max(left, self.range_max)
        return mask

    def _remove_marker_if_present(self, legend):
        try:
            self.plot.removeMarker(legend)
        except Exception:
            pass

    def _update_marker_lines(self):
        self._remove_marker_if_present(self.LEFT_MARKER)
        self._remove_marker_if_present(self.RIGHT_MARKER)
        self._remove_marker_if_present(self.EXCLUDE_LEFT_MARKER)
        self._remove_marker_if_present(self.EXCLUDE_RIGHT_MARKER)
        if self.range_min is not None:
            self.plot.addXMarker(self.range_min, legend=self.LEFT_MARKER, color="green")
        if self.range_max is not None:
            self.plot.addXMarker(self.range_max, legend=self.RIGHT_MARKER, color="orange")
        if self.exclude_min is not None:
            self.plot.addXMarker(self.exclude_min, legend=self.EXCLUDE_LEFT_MARKER, color="magenta")
        if self.exclude_max is not None:
            self.plot.addXMarker(self.exclude_max, legend=self.EXCLUDE_RIGHT_MARKER, color="cyan")

    def refresh_view(self):
        arrays = self._current_arrays()
        if arrays[0] is None or arrays[1] is None:
            return
        x, y = arrays
        curve_key = self.curveCombo.currentText()
        self.current_x = x
        self.current_y = y
        if (
            self.original_y is None
            or len(self.original_y) != len(y)
            or self._last_curve_key != curve_key
        ):
            self.original_y = np.array(y, copy=True)
            self.processed_y = np.array(y, copy=True)
            self.fit_y = None
            self._last_curve_key = curve_key

        mask = self._segment_mask(x, self.processed_y)
        self.plot.clear()
        self.plot.getXAxis().setLabel(self.xAxisCombo.currentText())
        self.plot.getYAxis().setLabel(self.curveCombo.currentText())
        self.plot.addCurve(x[mask], self.original_y[mask], legend="original", color="gray")
        self.plot.addCurve(x[mask], self.processed_y[mask], legend="processed", color="red")
        if self.fit_y is not None:
            fit_mask = self._selected_apply_mask(x, mask)
            if np.count_nonzero(fit_mask) >= 2:
                self.plot.addCurve(x[fit_mask], self.fit_y[fit_mask], legend="fit", color="blue", linestyle="--")
        self._update_marker_lines()

    def handle_plot_signal(self, ddict=None):
        if not ddict:
            return
        event_name = str(ddict.get("event", ""))
        if event_name not in ("mouseClicked", "plotClicked"):
            return
        x = ddict.get("x")
        if x is None:
            x = ddict.get("xdata")
        if x is None:
            return
        button = ddict.get("button", qt.Qt.LeftButton)
        button_text = str(button).lower()
        is_left = button in (qt.Qt.LeftButton, 1) or "left" in button_text
        if not is_left:
            return
        self._set_marker_from_x(float(x))

    def _compute_fit(self, x_fit, y_fit, x_eval, fit_type):
        if fit_type == "Linear":
            coeffs = np.polyfit(x_fit, y_fit, 1)
            return np.polyval(coeffs, x_eval), f"Linear fit: k={coeffs[0]:.4g}, b={coeffs[1]:.4g}"
        if fit_type == "Quadratic":
            coeffs = np.polyfit(x_fit, y_fit, 2)
            return np.polyval(coeffs, x_eval), f"Quadratic fit: a={coeffs[0]:.4g}, b={coeffs[1]:.4g}, c={coeffs[2]:.4g}"
        if fit_type == "Cubic":
            coeffs = np.polyfit(x_fit, y_fit, 3)
            return np.polyval(coeffs, x_eval), f"Cubic fit: a3={coeffs[0]:.4g}, a2={coeffs[1]:.4g}, a1={coeffs[2]:.4g}, a0={coeffs[3]:.4g}"
        if fit_type == "Quartic":
            coeffs = np.polyfit(x_fit, y_fit, 4)
            return np.polyval(coeffs, x_eval), f"Quartic fit: a4={coeffs[0]:.4g}, a3={coeffs[1]:.4g}, a2={coeffs[2]:.4g}, a1={coeffs[3]:.4g}, a0={coeffs[4]:.4g}"
        if fit_type == "Exponential":
            signs = np.sign(y_fit[np.abs(y_fit) > 0])
            if len(signs) == 0 or np.any(signs != signs[0]):
                raise ValueError("Exponential fit requires range values with the same sign and non-zero magnitude.")
            sign = signs[0]
            coeffs = np.polyfit(x_fit, np.log(np.abs(y_fit)), 1)
            fitted = sign * np.exp(np.polyval(coeffs, x_eval))
            return fitted, f"Exponential fit: y={sign:.0f}*exp({coeffs[0]:.4g}*x + {coeffs[1]:.4g})"
        if fit_type == "Logarithmic":
            if np.any(x_fit <= 0) or np.any(x_eval <= 0):
                raise ValueError("Logarithmic fit requires positive X values in the selected range.")
            coeffs = np.polyfit(np.log(x_fit), y_fit, 1)
            fitted = coeffs[0] * np.log(x_eval) + coeffs[1]
            return fitted, f"Log fit: y={coeffs[0]:.4g}*ln(x) + {coeffs[1]:.4g}"
        if fit_type == "Power":
            if np.any(x_fit <= 0) or np.any(x_eval <= 0):
                raise ValueError("Power fit requires positive X values in the selected range.")
            signs = np.sign(y_fit[np.abs(y_fit) > 0])
            if len(signs) == 0 or np.any(signs != signs[0]):
                raise ValueError("Power fit requires range values with the same sign and non-zero magnitude.")
            sign = signs[0]
            coeffs = np.polyfit(np.log(x_fit), np.log(np.abs(y_fit)), 1)
            fitted = sign * np.exp(coeffs[1]) * np.power(x_eval, coeffs[0])
            return fitted, f"Power fit: y={sign*np.exp(coeffs[1]):.4g}*x^{coeffs[0]:.4g}"
        raise ValueError(f"Unsupported fit type: {fit_type}")

    def fit_selected_range(self):
        arrays = self._current_arrays()
        if arrays[0] is None or arrays[1] is None:
            return
        x, _ = arrays
        mask = self._segment_mask(x, self.processed_y)
        fit_mask = self._selected_range_mask(x, mask)
        apply_mask = self._selected_apply_mask(x, mask)
        if np.count_nonzero(fit_mask) < 2:
            self.statusLabel.setText("Select a wider range on the graph first.")
            return
        if np.count_nonzero(apply_mask) < 2:
            self.statusLabel.setText("Select a valid application range on the graph first.")
            return
        fit_type = self.fitTypeCombo.currentText()
        try:
            fitted_segment, summary = self._compute_fit(
                x[fit_mask],
                self.processed_y[fit_mask],
                x[apply_mask],
                fit_type,
            )
        except (ValueError, np.linalg.LinAlgError) as exc:
            self.statusLabel.setText(str(exc))
            return
        self.fit_y = np.full(len(x), np.nan)
        self.fit_y[apply_mask] = fitted_segment
        self.statusLabel.setText(summary)
        self.refresh_view()

    def subtract_fit_from_curve(self):
        if self.fit_y is None:
            self.statusLabel.setText("Run fit first.")
            return
        valid = np.isfinite(self.fit_y)
        self.processed_y = np.array(self.processed_y, copy=True)
        self.processed_y[valid] = self.processed_y[valid] - self.fit_y[valid]
        self.statusLabel.setText("Fit subtracted from selected range.")
        self.refresh_view()

    def reset_processed_curve(self):
        arrays = self._current_arrays()
        if arrays[0] is None or arrays[1] is None:
            return
        _, y = arrays
        self.original_y = np.array(y, copy=True)
        self.processed_y = np.array(y, copy=True)
        self.fit_y = None
        self.refresh_view()

    def save_processing(self):
        if self.current_x is None or self.processed_y is None:
            return
        path, _ = qt.QFileDialog.getSaveFileName(self, "Save processing", "processing_result.h5", "HDF5 files (*.h5)", options=_dialog_options())
        if not path:
            return
        with h5py.File(path, "w") as h5:
            data_group = h5.create_group("data")
            data_group.create_dataset("x", data=self.current_x)
            data_group.create_dataset("original_y", data=self.original_y)
            data_group.create_dataset("processed_y", data=self.processed_y)
            if self.fit_y is not None:
                data_group.create_dataset("fit_y", data=self.fit_y)
            meta = {
                "source_path": self.source_path,
                "x_key": self.xAxisCombo.currentText(),
                "y_key": self.curveCombo.currentText(),
                "segment": self.segmentCombo.currentText(),
                "fit_type": self.fitTypeCombo.currentText(),
                "range_min": self.range_min,
                "range_max": self.range_max,
                "exclude_min": self.exclude_min,
                "exclude_max": self.exclude_max,
            }
            h5.create_dataset("processing", data=json.dumps(meta, ensure_ascii=False))
        self.statusLabel.setText(f"Saved processing to {Path(path).name}")

    def open_processing(self):
        path, _ = qt.QFileDialog.getOpenFileName(self, "Open processing", "", "HDF5 files (*.h5)", options=_dialog_options())
        if not path:
            return
        with h5py.File(path, "r") as h5:
            if "data" in h5:
                group = h5["data"]
                self.current_x = np.asarray(group["x"])
                self.original_y = np.asarray(group["original_y"])
                self.processed_y = np.asarray(group["processed_y"])
                self.fit_y = np.asarray(group["fit_y"]) if "fit_y" in group else None
            raw = h5["processing"][()]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            meta = json.loads(raw)
        self.source_path = meta.get("source_path", "")
        if self.source_path and Path(self.source_path).exists():
            self.filePathInput.setText(self.source_path)
            self.data_dict = self._read_h5_dict(self.source_path)
            keys = sorted(self.data_dict.keys())
            self.xAxisCombo.clear()
            self.curveCombo.clear()
            self.xAxisCombo.addItems(keys)
            self.curveCombo.addItems(keys)
            if meta.get("x_key") in self.data_dict:
                self.xAxisCombo.setCurrentText(meta["x_key"])
            if meta.get("y_key") in self.data_dict:
                self.curveCombo.setCurrentText(meta["y_key"])
        self.segmentCombo.setCurrentText(meta.get("segment", self.SEGMENT_OPTIONS[0]))
        saved_fit_type = meta.get("fit_type", self.FIT_OPTIONS[0])
        if saved_fit_type in self.FIT_OPTIONS:
            self.fitTypeCombo.setCurrentText(saved_fit_type)
        self.range_min = meta.get("range_min")
        self.range_max = meta.get("range_max")
        self.exclude_min = meta.get("exclude_min")
        self.exclude_max = meta.get("exclude_max")
        self.rangeMinLabel.setText("---" if self.range_min is None else f"{self.range_min:.6g}")
        self.rangeMaxLabel.setText("---" if self.range_max is None else f"{self.range_max:.6g}")
        self.excludeMinLabel.setText("---" if self.exclude_min is None else f"{self.exclude_min:.6g}")
        self.excludeMaxLabel.setText("---" if self.exclude_max is None else f"{self.exclude_max:.6g}")
        self.refresh_view()
        self.statusLabel.setText(f"Opened processing {Path(path).name}")
