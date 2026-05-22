from silx.gui import qt


class InputGainsPanel(qt.QFrame):
    """Panel with per-channel input gain sliders and auto-gain toggles."""

    stateChanged = qt.pyqtSignal(dict, dict)
    CHANNELS = ["Uref", "Umod", "Utpl", "Uhtr", "Uaux"]
    RANGE_LABELS = ["100 mV", "200 mV", "500 mV", "1 V", "2 V", "5 V", "10 V"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(qt.QFrame.StyledPanel)
        self.setFrameShadow(qt.QFrame.Plain)
        self._sliders = {}
        self._autos = {}
        self._updating_state = False
        self._build_ui()

    def _build_ui(self):
        root = qt.QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        for channel in self.CHANNELS:
            col = qt.QVBoxLayout()
            col.setSpacing(4)
            label = qt.QLabel(channel)
            label.setAlignment(qt.Qt.AlignHCenter)
            col.addWidget(label)

            slider = qt.QSlider(qt.Qt.Vertical)
            slider.setRange(0, len(self.RANGE_LABELS) - 1)
            slider.setInvertedAppearance(True)
            slider.setTickPosition(qt.QSlider.TicksBothSides)
            slider.setTickInterval(1)
            slider.setFixedHeight(110)
            col.addWidget(slider, alignment=qt.Qt.AlignHCenter)

            auto = qt.QCheckBox()
            auto.setChecked(True)
            col.addWidget(auto, alignment=qt.Qt.AlignHCenter)

            slider.valueChanged.connect(self._emit_state_changed)
            auto.toggled.connect(self._emit_state_changed)
            self._sliders[channel] = slider
            self._autos[channel] = auto
            root.addLayout(col)

        labels_col = qt.QVBoxLayout()
        labels_col.setSpacing(1)
        labels_col.addSpacing(24)
        for label in self.RANGE_LABELS:
            labels_col.addWidget(qt.QLabel(label))
        labels_col.addStretch()
        labels_col.addWidget(qt.QLabel("auto gain"))
        root.addLayout(labels_col)

    def _emit_state_changed(self, *args):
        if self._updating_state:
            return
        state = self.get_state()
        self.stateChanged.emit(state["ranges"], state["auto_gain"])

    def get_state(self):
        return {
            "ranges": {name: int(slider.value()) for name, slider in self._sliders.items()},
            "auto_gain": {name: bool(box.isChecked()) for name, box in self._autos.items()},
        }

    def set_state(self, ranges=None, auto_gain=None):
        ranges = ranges or {}
        auto_gain = auto_gain or {}
        self._updating_state = True
        try:
            for name, slider in self._sliders.items():
                slider.setValue(int(ranges.get(name, slider.value())))
            for name, box in self._autos.items():
                box.setChecked(bool(auto_gain.get(name, box.isChecked())))
        finally:
            self._updating_state = False
