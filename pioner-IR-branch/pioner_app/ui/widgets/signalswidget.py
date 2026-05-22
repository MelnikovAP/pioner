import numpy as np

from PyQt5 import QtWidgets as qt
from PyQt5.QtCore import Qt, QTimer

import pyqtgraph as pg

from pioner_app.hardware.daq_controller import get_daq_controller
from pioner_app.core.settings import settings


class SignalsWidget(qt.QWidget):

    def __init__(self, parent=None):
        """Initialize raw-signal display widget."""
        super().__init__(parent)

        self.ctrl = get_daq_controller()
        self.num_channels = 6
        self.points_per_read = 2000
        self._owns_acquisition = False
        self._window_seconds = 1.0

        main_layout = qt.QVBoxLayout(self)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("w")
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel('left', 'Volt')
        self.plot.setLabel('bottom', 'Time (s)')
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
        self.legend = self.plot.addLegend()
        main_layout.addWidget(self.plot)

        colors = ['r', 'g', 'b', 'c', 'm', 'k']
        names = ['Uref', 'Umod', 'Uhtr', 'Uaux', 'Utpl', 'Uhtrabs']
        self.curves = []

        for i, color in enumerate(colors):
            curve = self.plot.plot(
                pen=pg.mkPen(color, width=2),
                name=names[i],
                antialias=True,
                connect='finite',
            )
            self.curves.append(curve)

        for sample, label in self.legend.items:
            curve = sample.item
            label.mousePressEvent = self.make_toggle_fn(curve)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)

        controls = qt.QHBoxLayout()

        self.x_shift_slider = qt.QSlider(Qt.Horizontal)
        self.x_shift_slider.setRange(0, 20)
        controls.addWidget(qt.QLabel("X Shift (x50 ms):"))
        controls.addWidget(self.x_shift_slider)

        self.x_zoom_slider = qt.QSlider(Qt.Horizontal)
        self.x_zoom_slider.setRange(0, 9)
        self.x_zoom_slider.setValue(2)
        controls.addWidget(qt.QLabel("X Zoom:"))
        controls.addWidget(self.x_zoom_slider)

        self.y_range_slider = qt.QSlider(Qt.Horizontal)
        self.y_range_slider.setRange(0, 6)
        self.y_range_slider.setValue(1)
        controls.addWidget(qt.QLabel("Y Range:"))
        controls.addWidget(self.y_range_slider)

        self.acquire_button = qt.QPushButton("Acquire")
        self.acquire_button.clicked.connect(self.toggle_acquisition)
        controls.addWidget(self.acquire_button)

        main_layout.addLayout(controls)

    def _current_sample_rate(self):
        """Return current AI sample rate."""
        try:
            if self.ctrl and self.ctrl.em and getattr(self.ctrl.em, "ai", None):
                return float(getattr(self.ctrl.em.ai, "sample_rate", settings.sample_rate))
        except Exception:
            pass
        return float(getattr(settings, "sample_rate", 10000))

    def _points_for_window(self):
        """Pick number of points for the display window based on the actual sample rate."""
        fs = max(self._current_sample_rate(), 1.0)
        return max(1500, int(round(fs * self._window_seconds)))

    def make_toggle_fn(self, curve):
        """Create a show/hide handler for a curve from the legend."""
        def toggle(event):
            """Toggle visibility of the matching curve."""
            curve.setVisible(not curve.isVisible())
        return toggle

    def showEvent(self, event):
        """Automatically start acquisition when the tab is shown."""
        super().showEvent(event)
        self.start_acquisition()

    def hideEvent(self, event):
        """Stop the local timer when the tab is hidden."""
        super().hideEvent(event)
        self.stop_acquisition()

    def toggle_acquisition(self):
        """Toggle signal acquisition state."""
        if self.timer.isActive():
            self.stop_acquisition()
        else:
            self.start_acquisition()

    def start_acquisition(self):
        """Start acquisition or attach to an already running one."""
        if not self.ctrl.em:
            self.acquire_button.setText("No DAQ")
            self.acquire_button.setEnabled(False)
            return

        owner = self.ctrl.acquisition_owner()
        try:
            self.points_per_read = self._points_for_window()
            if self.ctrl.is_acquisition_running():
                self._owns_acquisition = owner == "signals"
                self.timer.start(1000)
                self.acquire_button.setText("Stop")
                return

            started = self.ctrl.start_acquisition(owner="signals", points_per_channel=self.points_per_read)
            self._owns_acquisition = bool(started)
            self.timer.start(1000)
            self.acquire_button.setText("Stop")
        except Exception as e:
            print(f"Start error: {e}")

    def stop_acquisition(self):
        """Stop acquisition if this widget owns it."""
        try:
            if self.ctrl.em and self._owns_acquisition:
                self.ctrl.stop_acquisition(owner="signals")
        except Exception as e:
            print(f"Stop error: {e}")

        self._owns_acquisition = False
        self.timer.stop()
        self.acquire_button.setText("Acquire")
        self.acquire_button.setEnabled(True)

    def update_plot(self):
        """Stub docstring."""
        self.points_per_read = self._points_for_window()
        data = self.ctrl.peek_data(points=self.points_per_read)

        if data is None:
            data = self.ctrl.get_last_data()
        if data is None:
            return

        display = np.asarray(data[-self.points_per_read:], dtype=float)
        fs = max(self._current_sample_rate(), 1.0)
        x = np.arange(len(display), dtype=float) / fs

        x_ranges = [2.0, 1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002]
        zoom_index = min(self.x_zoom_slider.value(), len(x_ranges) - 1)
        total_time = len(display) / fs
        window = min(x_ranges[zoom_index], max(total_time, 1.0 / fs))
        max_shift = max(total_time - window, 0.0)
        left = min(self.x_shift_slider.value() * 0.05, max_shift)
        right = left + window

        self.plot.setLabel('bottom', f'Time (s), fs={fs:.0f} Hz')
        self.plot.setXRange(left, right, padding=0.0)

        y_ranges = [10, 5, 1, 0.5, 0.1, 0.01, 0.005]
        y_range = y_ranges[self.y_range_slider.value()]
        self.plot.setYRange(-y_range, y_range, padding=0.0)

        for i in range(min(self.num_channels, display.shape[1])):
            self.curves[i].setData(x, display[:, i])
