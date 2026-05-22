import csv
from pathlib import Path

import h5py
import numpy as np
from silx.gui import qt
from silx.gui.plot import PlotWindow
from PyQt5.QtCore import QEvent

from pioner_app.ui.localization import tr, apply_language


class UniversalResultsWidget(qt.QWidget):
    FIT_OPTIONS = ["Linear", "Quadratic", "Cubic", "Quartic"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_dict = {}
        self.current_x = None
        self.current_y = None
        self.original_y = None
        self.processed_y = None
        self.fit_y = None
        self.fit_coeffs = None
        self.fit_equation = ""
        self.range_min = None
        self.range_max = None
        self.exclude_min = None
        self.exclude_max = None
        self._drag_start_x = None
        self._drag_mode = None
        self._build_ui()
        self._install_plot_click_filter()
        self._connect()
        apply_language(self)

    def _build_ui(self):
        root = qt.QHBoxLayout(self)

        left = qt.QVBoxLayout()
        root.addLayout(left, 0)

        source_group = qt.QGroupBox("Results source")
        source_layout = qt.QVBoxLayout(source_group)
        row = qt.QHBoxLayout()
        self.filePathInput = qt.QLineEdit()
        self.fileBrowseButton = qt.QToolButton()
        self.fileBrowseButton.setText("...")
        row.addWidget(self.filePathInput, 1)
        row.addWidget(self.fileBrowseButton)
        source_layout.addLayout(row)
        self.openButton = qt.QPushButton("Open result file")
        source_layout.addWidget(self.openButton)
        left.addWidget(source_group)

        axes_group = qt.QGroupBox("Axes")
        axes_layout = qt.QFormLayout(axes_group)
        self.xAxisCombo = qt.QComboBox()
        self.yAxisCombo = qt.QComboBox()
        axes_layout.addRow("X axis", self.xAxisCombo)
        axes_layout.addRow("Y axis", self.yAxisCombo)
        left.addWidget(axes_group)

        process_group = qt.QGroupBox("Processing")
        process_layout = qt.QFormLayout(process_group)
        self.fitTypeCombo = qt.QComboBox()
        self.fitTypeCombo.addItems(self.FIT_OPTIONS)
        self.smoothWindow = qt.QSpinBox()
        self.smoothWindow.setRange(1, 501)
        self.smoothWindow.setSingleStep(2)
        self.smoothWindow.setValue(1)
        self.rangeMinLabel = qt.QLabel("---")
        self.rangeMaxLabel = qt.QLabel("---")
        self.excludeMinLabel = qt.QLabel("---")
        self.excludeMaxLabel = qt.QLabel("---")
        process_layout.addRow("Fit type", self.fitTypeCombo)
        process_layout.addRow("Smooth window", self.smoothWindow)
        process_layout.addRow("Fit min", self.rangeMinLabel)
        process_layout.addRow("Fit max", self.rangeMaxLabel)
        process_layout.addRow("Exclude min", self.excludeMinLabel)
        process_layout.addRow("Exclude max", self.excludeMaxLabel)
        left.addWidget(process_group)

        button_group = qt.QGroupBox("Actions")
        button_layout = qt.QVBoxLayout(button_group)
        self.fitButton = qt.QPushButton("Fit range")
        self.subtractButton = qt.QPushButton("Subtract fit")
        self.resetButton = qt.QPushButton("Reset curve")
        self.clearRangeButton = qt.QPushButton("Clear fit range")
        self.clearExcludeButton = qt.QPushButton("Clear exclude")
        button_layout.addWidget(self.fitButton)
        button_layout.addWidget(self.subtractButton)
        button_layout.addWidget(self.resetButton)
        button_layout.addWidget(self.clearRangeButton)
        button_layout.addWidget(self.clearExcludeButton)
        left.addWidget(button_group)
        left.addStretch(1)

        right = qt.QVBoxLayout()
        root.addLayout(right, 1)
        self.plot = PlotWindow(resetzoom=True)
        self.plot.setGraphGrid("major")
        self.plot.setActiveCurveHandling(False)
        right.addWidget(self.plot, 1)
        self.statusLabel = qt.QLabel("Open a slow-heating CSV or fast-heating H5 file.")
        self.statusLabel.setWordWrap(True)
        right.addWidget(self.statusLabel)
        self.equationLabel = qt.QLabel("")
        self.equationLabel.setWordWrap(True)
        self.equationLabel.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        right.addWidget(self.equationLabel)

    def _connect(self):
        self.fileBrowseButton.clicked.connect(self.browse_file)
        self.openButton.clicked.connect(self.load_selected_file)
        self.xAxisCombo.currentTextChanged.connect(self.refresh_view)
        self.yAxisCombo.currentTextChanged.connect(self.refresh_view)
        self.smoothWindow.valueChanged.connect(self.refresh_view)
        self.fitButton.clicked.connect(self.fit_selected_range)
        self.subtractButton.clicked.connect(self.subtract_fit)
        self.resetButton.clicked.connect(self.reset_curve)
        self.clearRangeButton.clicked.connect(self.clear_range)
        self.clearExcludeButton.clicked.connect(self.clear_exclude)

    def _install_plot_click_filter(self):
        backend = None
        try:
            backend = self.plot.getWidgetHandle()
        except Exception:
            backend = None
        if backend is not None:
            backend.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and getattr(event, 'button', lambda: None)() == qt.Qt.LeftButton:
            x = self._pixel_to_x(event)
            if x is not None:
                self._drag_start_x = x
                modifiers = event.modifiers() if hasattr(event, 'modifiers') else qt.Qt.NoModifier
                self._drag_mode = 'exclude' if modifiers & qt.Qt.ControlModifier else 'range'
                return True
        if event.type() == QEvent.MouseButtonRelease and getattr(event, 'button', lambda: None)() == qt.Qt.LeftButton:
            if self._drag_start_x is not None:
                x = self._pixel_to_x(event)
                if x is not None:
                    if self._drag_mode == 'exclude':
                        self.exclude_min, self.exclude_max = sorted((float(self._drag_start_x), float(x)))
                    else:
                        self.range_min, self.range_max = sorted((float(self._drag_start_x), float(x)))
                    self._update_range_labels()
                    self.refresh_view()
                self._drag_start_x = None
                self._drag_mode = None
                return True
        return super().eventFilter(obj, event)

    def _pixel_to_x(self, event):
        pos = event.position() if hasattr(event, 'position') else event.pos()
        data_pos = self.plot.pixelToData(float(pos.x()), float(pos.y()))
        if data_pos is None or len(data_pos) < 1:
            return None
        return float(data_pos[0])

    def browse_file(self):
        path, _ = qt.QFileDialog.getOpenFileName(self, tr('Open result file'), str(Path.cwd()), tr('Result files (*.h5 *.hdf5 *.csv)'))
        if path:
            self.filePathInput.setText(path)

    def load_selected_file(self):
        path = self.filePathInput.text().strip()
        if not path:
            return
        try:
            self.data_dict = self._load_file(path)
        except Exception as exc:
            qt.QMessageBox.critical(self, tr('Result file'), str(exc))
            return
        keys = list(self.data_dict.keys())
        self.xAxisCombo.clear()
        self.yAxisCombo.clear()
        self.xAxisCombo.addItems(keys)
        self.yAxisCombo.addItems(keys)
        if 'time_s' in self.data_dict:
            self.xAxisCombo.setCurrentText('time_s')
        elif keys:
            self.xAxisCombo.setCurrentIndex(0)
        for preferred in ('amplitude_c', 'amplitude_mv', 'temp', 'Thtr'):
            if preferred in self.data_dict:
                self.yAxisCombo.setCurrentText(preferred)
                break
        self.range_min = self.range_max = self.exclude_min = self.exclude_max = None
        self.fit_coeffs = None
        self.fit_equation = ""
        self._update_range_labels()
        self.refresh_view()
        self.statusLabel.setText(tr(f'Loaded {Path(path).name}'))

    def _load_file(self, path):
        suffix = Path(path).suffix.lower()
        if suffix in ('.h5', '.hdf5'):
            return self._load_h5(path)
        if suffix == '.csv':
            return self._load_csv(path)
        raise ValueError(tr('Unsupported result file type.'))

    def _load_h5(self, path):
        result = {}
        with h5py.File(path, 'r') as h5:
            def visit(name, obj):
                if isinstance(obj, h5py.Dataset):
                    arr = np.asarray(obj[()])
                    if arr.ndim == 1 and np.issubdtype(arr.dtype, np.number):
                        result[name.split('/')[-1]] = arr.astype(float)
            h5.visititems(visit)
        if not result:
            raise ValueError(tr('No 1D numeric datasets found in the H5 file.'))
        return result

    def _load_csv(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            raise ValueError(tr('CSV file is empty.'))
        result = {}
        for key in reader.fieldnames or []:
            values = []
            ok = True
            for row in rows:
                try:
                    values.append(float(row[key]))
                except Exception:
                    ok = False
                    break
            if ok:
                result[key] = np.asarray(values, dtype=float)
        if not result:
            raise ValueError(tr('No numeric columns found in the CSV file.'))
        return result

    def _selected_arrays(self):
        x_key = self.xAxisCombo.currentText()
        y_key = self.yAxisCombo.currentText()
        if not x_key or not y_key or x_key not in self.data_dict or y_key not in self.data_dict:
            return None, None
        x = np.asarray(self.data_dict[x_key], dtype=float)
        y = np.asarray(self.data_dict[y_key], dtype=float)
        n = min(len(x), len(y))
        if n == 0:
            return None, None
        return x[:n], y[:n]

    def _smoothed(self, y):
        window = int(self.smoothWindow.value())
        if window <= 1 or len(y) < window:
            return y.copy()
        if window % 2 == 0:
            window += 1
        kernel = np.ones(window, dtype=float) / float(window)
        return np.convolve(y, kernel, mode='same')

    def _selected_fit_mask(self, x):
        mask = np.ones(len(x), dtype=bool)
        if self.range_min is not None and self.range_max is not None:
            lo, hi = sorted((self.range_min, self.range_max))
            mask &= (x >= lo) & (x <= hi)
        if self.exclude_min is not None and self.exclude_max is not None:
            lo, hi = sorted((self.exclude_min, self.exclude_max))
            mask &= ~((x >= lo) & (x <= hi))
        return mask

    def _update_range_labels(self):
        self.rangeMinLabel.setText('---' if self.range_min is None else f'{self.range_min:.6g}')
        self.rangeMaxLabel.setText('---' if self.range_max is None else f'{self.range_max:.6g}')
        self.excludeMinLabel.setText('---' if self.exclude_min is None else f'{self.exclude_min:.6g}')
        self.excludeMaxLabel.setText('---' if self.exclude_max is None else f'{self.exclude_max:.6g}')

    def clear_range(self):
        self.range_min = self.range_max = None
        self._update_range_labels()
        self.refresh_view()

    def clear_exclude(self):
        self.exclude_min = self.exclude_max = None
        self._update_range_labels()
        self.refresh_view()

    def _poly_degree(self):
        return {"Linear": 1, "Quadratic": 2, "Cubic": 3, "Quartic": 4}.get(self.fitTypeCombo.currentText(), 1)

    def _format_equation(self, coeffs):
        if coeffs is None:
            return ""
        degree = len(coeffs) - 1
        terms = []
        for i, coeff in enumerate(coeffs):
            power = degree - i
            if abs(coeff) < 1e-15:
                continue
            sign = '-' if coeff < 0 else '+'
            value = f"{abs(coeff):.6g}"
            if power == 0:
                term = value
            elif power == 1:
                term = f"{value}?x"
            else:
                term = f"{value}?x^{power}"
            if not terms:
                terms.append(term if coeff >= 0 else f"- {term}")
            else:
                terms.append(f"{sign} {term}")
        rhs = ' '.join(terms) if terms else '0'
        return f"y = {rhs}"

    def fit_selected_range(self):
        x, y = self._selected_arrays()
        if x is None:
            return
        y_proc = self._smoothed(self.processed_y if self.processed_y is not None else y)
        mask = self._selected_fit_mask(x)
        if np.count_nonzero(mask) < self._poly_degree() + 1:
            self.statusLabel.setText(tr('Not enough points in the selected fit range.'))
            return
        coeffs = np.polyfit(x[mask], y_proc[mask], self._poly_degree())
        self.fit_coeffs = np.asarray(coeffs, dtype=float)
        self.fit_equation = self._format_equation(self.fit_coeffs)
        self.fit_y = np.polyval(coeffs, x)
        self.refresh_view()
        self.statusLabel.setText(tr('Fit updated.'))
        self.equationLabel.setText(self.fit_equation)

    def subtract_fit(self):
        if self.fit_y is None:
            self.fit_selected_range()
            if self.fit_y is None:
                return
        if self.processed_y is None:
            x, y = self._selected_arrays()
            if x is None:
                return
            self.processed_y = y.copy()
        self.processed_y = np.asarray(self.processed_y, dtype=float) - np.asarray(self.fit_y, dtype=float)
        self.fit_y = None
        self.fit_coeffs = None
        self.fit_equation = ""
        self.refresh_view()
        self.equationLabel.setText("")
        self.statusLabel.setText(tr('Fit subtracted from the curve.'))

    def reset_curve(self):
        self.processed_y = None
        self.fit_y = None
        self.fit_coeffs = None
        self.fit_equation = ""
        self.refresh_view()
        self.equationLabel.setText("")
        self.statusLabel.setText(tr('Curve reset.'))

    def refresh_view(self):
        self.plot.clear()
        x, y = self._selected_arrays()
        if x is None:
            return
        self.current_x = x
        self.original_y = y
        if self.processed_y is not None and len(self.processed_y) != len(y):
            self.processed_y = None
        curve_y = self.processed_y if self.processed_y is not None else y
        curve_y = self._smoothed(np.asarray(curve_y, dtype=float))
        self.plot.addCurve(x, curve_y, legend='data', color='blue', linewidth=1.5)
        if self.fit_y is not None and len(self.fit_y) == len(x):
            self.plot.addCurve(x, self.fit_y, legend='fit', color='red', linewidth=1.2)
        if self.range_min is not None and self.range_max is not None:
            lo, hi = sorted((self.range_min, self.range_max))
            self.plot.addXMarker(lo, legend='fit min', color='black')
            self.plot.addXMarker(hi, legend='fit max', color='black')
        if self.exclude_min is not None and self.exclude_max is not None:
            lo, hi = sorted((self.exclude_min, self.exclude_max))
            self.plot.addXMarker(lo, legend='exclude min', color='gray')
            self.plot.addXMarker(hi, legend='exclude max', color='gray')
        self.plot.getXAxis().setLabel(self.xAxisCombo.currentText())
        self.plot.getYAxis().setLabel(self.yAxisCombo.currentText())
        self.equationLabel.setText(self.fit_equation or "")
