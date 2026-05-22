import csv
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
from silx.gui import qt
from silx.gui.plot import PlotWindow


@dataclass
class PeakResult:
    index: int
    onset_x: float
    apex_x: float
    apex_y: float
    end_x: float
    height: float
    area: float


class EvaluationWidget(qt.QWidget):
    BASELINE_OPTIONS = ["Linear endpoints", "Quadratic trend", "None"]
    PEAK_POLARITY = ["Positive peaks", "Negative peaks"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_dict = {}
        self.current_path = None
        self.analysis_range = None
        self.original_x = None
        self.original_y = None
        self.smoothed_y = None
        self.baseline_y = None
        self.corrected_y = None
        self.derivative_y = None
        self.peaks = []
        self._drag_start_x = None
        self._build_ui()
        self._install_plot_click_filter()
        self._connect()

    def _build_ui(self):
        self.setWindowTitle("PIONER Lab Evaluation")
        root = qt.QHBoxLayout(self)

        left = qt.QVBoxLayout()
        root.addLayout(left, 0)

        source_group = qt.QGroupBox("Data source")
        source_layout = qt.QVBoxLayout(source_group)
        source_row = qt.QHBoxLayout()
        self.file_path = qt.QLineEdit()
        self.browse_button = qt.QToolButton()
        self.browse_button.setText("...")
        source_row.addWidget(self.file_path, 1)
        source_row.addWidget(self.browse_button)
        source_layout.addLayout(source_row)
        self.open_button = qt.QPushButton("Open file")
        source_layout.addWidget(self.open_button)
        left.addWidget(source_group)

        axes_group = qt.QGroupBox("Axes")
        axes_layout = qt.QFormLayout(axes_group)
        self.x_combo = qt.QComboBox()
        self.y_combo = qt.QComboBox()
        axes_layout.addRow("Abscissa", self.x_combo)
        axes_layout.addRow("Ordinate", self.y_combo)
        left.addWidget(axes_group)

        proc_group = qt.QGroupBox("Processing")
        proc_layout = qt.QFormLayout(proc_group)
        self.smooth_spin = qt.QSpinBox()
        self.smooth_spin.setRange(1, 1001)
        self.smooth_spin.setSingleStep(2)
        self.smooth_spin.setValue(11)
        self.baseline_combo = qt.QComboBox()
        self.baseline_combo.addItems(self.BASELINE_OPTIONS)
        self.polarity_combo = qt.QComboBox()
        self.polarity_combo.addItems(self.PEAK_POLARITY)
        self.peak_limit_spin = qt.QSpinBox()
        self.peak_limit_spin.setRange(1, 100)
        self.peak_limit_spin.setValue(8)
        self.prominence_spin = qt.QDoubleSpinBox()
        self.prominence_spin.setRange(0.0, 1e9)
        self.prominence_spin.setDecimals(6)
        self.prominence_spin.setValue(0.01)
        self.range_min_label = qt.QLabel("---")
        self.range_max_label = qt.QLabel("---")
        proc_layout.addRow("Smooth window", self.smooth_spin)
        proc_layout.addRow("Baseline", self.baseline_combo)
        proc_layout.addRow("Peak type", self.polarity_combo)
        proc_layout.addRow("Max peaks", self.peak_limit_spin)
        proc_layout.addRow("Min prominence", self.prominence_spin)
        proc_layout.addRow("Range min", self.range_min_label)
        proc_layout.addRow("Range max", self.range_max_label)
        left.addWidget(proc_group)

        action_group = qt.QGroupBox("Actions")
        action_layout = qt.QVBoxLayout(action_group)
        self.refresh_button = qt.QPushButton("Refresh analysis")
        self.auto_peaks_button = qt.QPushButton("Find peaks")
        self.clear_peaks_button = qt.QPushButton("Clear peaks")
        self.reset_range_button = qt.QPushButton("Clear range")
        self.export_button = qt.QPushButton("Export peak table")
        action_layout.addWidget(self.refresh_button)
        action_layout.addWidget(self.auto_peaks_button)
        action_layout.addWidget(self.clear_peaks_button)
        action_layout.addWidget(self.reset_range_button)
        action_layout.addWidget(self.export_button)
        left.addWidget(action_group)

        help_label = qt.QLabel(
            "Drag with left mouse on the main plot to set the analysis range. "
            "The app calculates baseline, onset, apex, endset, peak area, and lets you switch X/Y axes."
        )
        help_label.setWordWrap(True)
        left.addWidget(help_label)
        left.addStretch(1)

        right = qt.QVBoxLayout()
        root.addLayout(right, 1)

        self.main_plot = PlotWindow(resetzoom=True)
        self.main_plot.setGraphGrid("major")
        self.main_plot.setGraphTitle("Signal evaluation")
        self.main_plot.setGraphXLabel("X")
        self.main_plot.setGraphYLabel("Y")
        right.addWidget(self.main_plot, 3)

        self.derivative_plot = PlotWindow(resetzoom=True)
        self.derivative_plot.setGraphGrid("major")
        self.derivative_plot.setGraphTitle("Corrected signal / derivative")
        self.derivative_plot.setGraphXLabel("X")
        self.derivative_plot.setGraphYLabel("dY/dX")
        right.addWidget(self.derivative_plot, 2)

        self.peak_table = qt.QTableWidget(0, 7)
        self.peak_table.setHorizontalHeaderLabels([
            "#", "Onset", "Apex X", "Apex Y", "Endset", "Height", "Area"
        ])
        self.peak_table.horizontalHeader().setStretchLastSection(True)
        right.addWidget(self.peak_table, 1)

        self.status_label = qt.QLabel("Open a CSV or H5 result file to start evaluation.")
        self.status_label.setWordWrap(True)
        right.addWidget(self.status_label)

    def _connect(self):
        self.browse_button.clicked.connect(self.browse_file)
        self.open_button.clicked.connect(self.load_selected_file)
        self.x_combo.currentTextChanged.connect(self.refresh_analysis)
        self.y_combo.currentTextChanged.connect(self.refresh_analysis)
        self.smooth_spin.valueChanged.connect(self.refresh_analysis)
        self.baseline_combo.currentTextChanged.connect(self.refresh_analysis)
        self.refresh_button.clicked.connect(self.refresh_analysis)
        self.auto_peaks_button.clicked.connect(self.detect_peaks)
        self.clear_peaks_button.clicked.connect(self.clear_peaks)
        self.reset_range_button.clicked.connect(self.clear_range)
        self.export_button.clicked.connect(self.export_peaks)

    def _install_plot_click_filter(self):
        backend = None
        try:
            backend = self.main_plot.getWidgetHandle()
        except Exception:
            backend = None
        if backend is not None:
            backend.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == qt.QEvent.MouseButtonPress and getattr(event, "button", lambda: None)() == qt.Qt.LeftButton:
            x = self._pixel_to_x(event)
            if x is not None:
                self._drag_start_x = x
                return True
        if event.type() == qt.QEvent.MouseButtonRelease and getattr(event, "button", lambda: None)() == qt.Qt.LeftButton:
            if self._drag_start_x is not None:
                x = self._pixel_to_x(event)
                if x is not None:
                    self.analysis_range = tuple(sorted((float(self._drag_start_x), float(x))))
                    self._update_range_labels()
                    self.refresh_analysis()
                self._drag_start_x = None
                return True
        return super().eventFilter(obj, event)

    def _pixel_to_x(self, event):
        pos = event.position() if hasattr(event, "position") else event.pos()
        data_pos = self.main_plot.pixelToData(float(pos.x()), float(pos.y()))
        if data_pos is None or len(data_pos) < 1:
            return None
        return float(data_pos[0])

    def browse_file(self):
        path, _ = qt.QFileDialog.getOpenFileName(
            self,
            "Open result file",
            str(Path.cwd()),
            "Result files (*.csv *.h5 *.hdf5)"
        )
        if path:
            self.file_path.setText(path)

    def load_selected_file(self):
        path = self.file_path.text().strip()
        if not path:
            return
        try:
            data_dict = self._load_file(path)
        except Exception as exc:
            qt.QMessageBox.critical(self, "Load error", str(exc))
            return

        self.current_path = path
        self.data_dict = data_dict
        keys = list(data_dict.keys())
        self.x_combo.clear()
        self.y_combo.clear()
        self.x_combo.addItems(keys)
        self.y_combo.addItems(keys)

        preferred_x = next((key for key in ("time(ms)", "time_s", "temp", "Thtr") if key in data_dict), keys[0])
        preferred_y = next((key for key in ("temp", "Thtr", "Taux", "temp-hr", "Ihtr", "Ref") if key in data_dict), keys[min(1, len(keys) - 1)])
        self.x_combo.setCurrentText(preferred_x)
        self.y_combo.setCurrentText(preferred_y)
        self.analysis_range = None
        self.peaks = []
        self._update_range_labels()
        self.refresh_analysis()
        self.status_label.setText(f"Loaded {Path(path).name}")

    def _load_file(self, path):
        suffix = Path(path).suffix.lower()
        if suffix == ".csv":
            return self._load_csv(path)
        if suffix in (".h5", ".hdf5"):
            return self._load_h5(path)
        raise ValueError("Unsupported file type.")

    def _load_csv(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        if not rows:
            raise ValueError("CSV file is empty.")

        result = {}
        for field in reader.fieldnames or []:
            values = []
            numeric = True
            for row in rows:
                try:
                    values.append(float(row[field]))
                except Exception:
                    numeric = False
                    break
            if numeric:
                result[field] = np.asarray(values, dtype=float)
        if not result:
            raise ValueError("No numeric columns found in CSV.")
        return result

    def _load_h5(self, path):
        result = {}
        with h5py.File(path, "r") as h5:
            def visit(name, obj):
                if isinstance(obj, h5py.Dataset):
                    arr = np.asarray(obj[()])
                    if arr.ndim == 1 and np.issubdtype(arr.dtype, np.number):
                        result[name.split("/")[-1]] = arr.astype(float)
            h5.visititems(visit)
        if not result:
            raise ValueError("No 1D numeric datasets found in H5.")
        return result

    def _selected_arrays(self):
        x_key = self.x_combo.currentText()
        y_key = self.y_combo.currentText()
        if x_key not in self.data_dict or y_key not in self.data_dict:
            return None, None
        x = np.asarray(self.data_dict[x_key], dtype=float)
        y = np.asarray(self.data_dict[y_key], dtype=float)
        n = min(len(x), len(y))
        if n == 0:
            return None, None
        x = x[:n]
        y = y[:n]
        order = np.argsort(x, kind="mergesort")
        return x[order], y[order]

    def _smooth(self, y):
        window = int(self.smooth_spin.value())
        if window <= 1 or len(y) < 3:
            return y.copy()
        if window % 2 == 0:
            window += 1
        window = min(window, len(y) if len(y) % 2 == 1 else len(y) - 1)
        if window < 3:
            return y.copy()
        kernel = np.ones(window, dtype=float) / float(window)
        padded = np.pad(y, (window // 2, window // 2), mode="edge")
        return np.convolve(padded, kernel, mode="valid")

    def _analysis_mask(self, x):
        if self.analysis_range is None:
            return np.ones(len(x), dtype=bool)
        lo, hi = self.analysis_range
        return (x >= lo) & (x <= hi)

    def _compute_baseline(self, x, y):
        mode = self.baseline_combo.currentText()
        if mode == "None":
            return np.zeros_like(y)
        if len(x) < 2:
            return np.zeros_like(y)
        if mode == "Linear endpoints":
            return np.interp(x, [x[0], x[-1]], [y[0], y[-1]])

        degree = 2
        if len(x) <= degree:
            return np.interp(x, [x[0], x[-1]], [y[0], y[-1]])
        coeffs = np.polyfit(x, y, degree)
        return np.polyval(coeffs, x)

    def refresh_analysis(self):
        x, y = self._selected_arrays()
        if x is None:
            return

        mask = self._analysis_mask(x)
        if np.count_nonzero(mask) < 3:
            self.status_label.setText("Analysis range is too small.")
            return

        x_sel = x[mask]
        y_sel = y[mask]
        y_smooth = self._smooth(y_sel)
        baseline = self._compute_baseline(x_sel, y_smooth)
        corrected = y_smooth - baseline
        derivative = np.gradient(corrected, x_sel) if len(x_sel) > 2 else np.zeros_like(corrected)

        self.original_x = x_sel
        self.original_y = y_sel
        self.smoothed_y = y_smooth
        self.baseline_y = baseline
        self.corrected_y = corrected
        self.derivative_y = derivative

        self._draw_curves()
        if self.peaks:
            self.detect_peaks()
        else:
            self._update_peak_table()

    def _draw_curves(self):
        x = self.original_x
        if x is None:
            return

        self.main_plot.clear()
        self.main_plot.addCurve(x, self.original_y, legend="Raw", color="gray")
        self.main_plot.addCurve(x, self.smoothed_y, legend="Smoothed", color="blue", linewidth=2)
        self.main_plot.addCurve(x, self.baseline_y, legend="Baseline", color="orange", linewidth=2)
        self.main_plot.addCurve(x, self.corrected_y + self.baseline_y, legend="Processed", color="red", linewidth=2)

        self.derivative_plot.clear()
        self.derivative_plot.addCurve(x, self.corrected_y, legend="Corrected", color="green", linewidth=2)
        self.derivative_plot.addCurve(x, self.derivative_y, legend="Derivative", color="magenta", linewidth=1)

        if self.analysis_range is not None:
            lo, hi = self.analysis_range
            ymin = float(np.min(self.original_y))
            ymax = float(np.max(self.original_y))
            self.main_plot.addCurve([lo, lo], [ymin, ymax], legend="Range start", color="black", linestyle="--")
            self.main_plot.addCurve([hi, hi], [ymin, ymax], legend="Range end", color="black", linestyle="--")

        self._draw_peak_markers()

    def _draw_peak_markers(self):
        if self.original_x is None:
            return
        for peak in self.peaks:
            self.main_plot.addXMarker(peak.onset_x, legend=f"Onset {peak.index}", text=f"Onset {peak.index}", color="darkGreen")
            self.main_plot.addXMarker(peak.apex_x, legend=f"Peak {peak.index}", text=f"Peak {peak.index}", color="red")
            self.main_plot.addXMarker(peak.end_x, legend=f"End {peak.index}", text=f"End {peak.index}", color="darkBlue")

    def detect_peaks(self):
        if self.original_x is None or len(self.original_x) < 5:
            return

        signal = self.corrected_y.copy()
        positive = self.polarity_combo.currentText() == "Positive peaks"
        work = signal if positive else -signal
        prominence = float(self.prominence_spin.value())
        limit = int(self.peak_limit_spin.value())

        candidates = []
        for idx in range(1, len(work) - 1):
            if work[idx] <= work[idx - 1] or work[idx] < work[idx + 1]:
                continue
            local_prominence = work[idx] - max(min(work[max(0, idx - 10):idx + 1]), min(work[idx: min(len(work), idx + 11)]))
            if local_prominence < prominence:
                continue
            candidates.append((idx, work[idx], local_prominence))

        candidates.sort(key=lambda item: item[2], reverse=True)
        selected = sorted(candidates[:limit], key=lambda item: item[0])

        peaks = []
        for peak_number, (apex_idx, _, _) in enumerate(selected, start=1):
            left = apex_idx
            while left > 1 and work[left] > 0:
                if work[left - 1] <= 0:
                    break
                left -= 1
            right = apex_idx
            while right < len(work) - 2 and work[right] > 0:
                if work[right + 1] <= 0:
                    break
                right += 1

            onset_x = self._estimate_onset(left, apex_idx, positive)
            end_x = float(self.original_x[right])
            apex_x = float(self.original_x[apex_idx])
            apex_y = float(self.smoothed_y[apex_idx])
            height = float(signal[apex_idx]) if positive else float(-signal[apex_idx])
            area = float(np.trapz(signal[left:right + 1], self.original_x[left:right + 1]))
            if not positive:
                area = -area
            peaks.append(PeakResult(
                index=peak_number,
                onset_x=float(onset_x),
                apex_x=apex_x,
                apex_y=apex_y,
                end_x=end_x,
                height=height,
                area=area,
            ))

        self.peaks = peaks
        self._draw_curves()
        self._update_peak_table()
        self.status_label.setText(f"Detected {len(peaks)} peak(s)")

    def _estimate_onset(self, left_idx, apex_idx, positive):
        x = self.original_x
        baseline = self.baseline_y
        smoothed = self.smoothed_y
        derivative = np.gradient(smoothed, x)
        segment = derivative[left_idx:apex_idx + 1]
        if len(segment) == 0:
            return float(x[left_idx])
        tangent_idx_local = int(np.argmax(segment) if positive else np.argmin(segment))
        tangent_idx = left_idx + tangent_idx_local
        slope = float(derivative[tangent_idx])
        if abs(slope) < 1e-12:
            return float(x[left_idx])
        x0 = float(x[tangent_idx])
        y0 = float(smoothed[tangent_idx])
        b0 = float(baseline[tangent_idx])
        onset_x = x0 - (y0 - b0) / slope
        return float(np.clip(onset_x, x[left_idx], x[apex_idx]))

    def clear_peaks(self):
        self.peaks = []
        self._draw_curves()
        self._update_peak_table()
        self.status_label.setText("Peak markers cleared.")

    def clear_range(self):
        self.analysis_range = None
        self._update_range_labels()
        self.refresh_analysis()

    def _update_range_labels(self):
        if self.analysis_range is None:
            self.range_min_label.setText("---")
            self.range_max_label.setText("---")
            return
        lo, hi = self.analysis_range
        self.range_min_label.setText(f"{lo:.6g}")
        self.range_max_label.setText(f"{hi:.6g}")

    def _update_peak_table(self):
        self.peak_table.setRowCount(len(self.peaks))
        for row, peak in enumerate(self.peaks):
            values = [
                peak.index,
                peak.onset_x,
                peak.apex_x,
                peak.apex_y,
                peak.end_x,
                peak.height,
                peak.area,
            ]
            for col, value in enumerate(values):
                item = qt.QTableWidgetItem(f"{value:.6g}" if isinstance(value, float) else str(value))
                self.peak_table.setItem(row, col, item)
        self.peak_table.resizeColumnsToContents()

    def export_peaks(self):
        if not self.peaks:
            qt.QMessageBox.information(self, "Export peaks", "No peak results to export.")
            return
        path, _ = qt.QFileDialog.getSaveFileName(
            self,
            "Export peak table",
            str(Path.cwd() / "evaluation_peaks.csv"),
            "CSV files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["index", "onset_x", "apex_x", "apex_y", "end_x", "height", "area"])
            for peak in self.peaks:
                writer.writerow([peak.index, peak.onset_x, peak.apex_x, peak.apex_y, peak.end_x, peak.height, peak.area])
        self.status_label.setText(f"Peak table exported to {Path(path).name}")


class EvaluationWindow(qt.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PIONER Lab Evaluation")
        self.resize(1600, 950)
        self.widget = EvaluationWidget(self)
        self.setCentralWidget(self.widget)
