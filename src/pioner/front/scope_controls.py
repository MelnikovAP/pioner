"""Bondar-style scope controls + display helpers, shared across windows.

Extracted from the old standalone streaming window so the same scope
panel (X scale / X shift / Y span sliders + per-channel checkboxes) can
be reused inside the main PIONER window without duplication.

The widget is presentation-only: it owns no data and no timer. It
emits :pyattr:`ScopeControls.changed` whenever any control moves; the
host pulls the current state through the public accessors on its next
refresh tick.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from silx.gui import qt

from pioner.shared.settings import UISettings


def downsample_for_display(arr: np.ndarray, max_points: int) -> np.ndarray:
    """Decimate ``arr`` so it has at most ``max_points`` rows.

    Uses stride-based picking, not averaging -- preserves spikes and is
    fast enough to run on the UI thread.
    """
    n = arr.shape[0]
    if n <= max_points:
        return arr
    stride = max(1, n // max_points)
    return arr[::stride]


def log_slider_value(position: int, lo: float, hi: float, resolution: int = 1000) -> float:
    """Map slider position [0..resolution] to log-spaced value [lo..hi]."""
    if lo <= 0 or hi <= 0:
        # Linear fallback for ranges that include zero / negative.
        return lo + (hi - lo) * (position / float(resolution))
    return lo * (hi / lo) ** (position / float(resolution))


def log_slider_position(value: float, lo: float, hi: float, resolution: int = 1000) -> int:
    """Inverse of :func:`log_slider_value` -- find the slider position closest to ``value``."""
    if lo <= 0 or hi <= 0 or value <= 0:
        if hi == lo:
            return 0
        return int(round((value - lo) / (hi - lo) * resolution))
    if hi == lo or value <= lo:
        return 0
    return int(round(math.log(value / lo) / math.log(hi / lo) * resolution))


class ScopeControls(qt.QGroupBox):
    """Bondar-style scope controls: X scale / X shift / Y span sliders + channel checkboxes.

    Emits :pyattr:`changed` whenever any control value changes; the
    parent pulls the current state from the public accessors and applies
    it to the plot on its next refresh tick.
    """

    changed = qt.pyqtSignal()  # type: ignore[attr-defined]

    _SLIDER_RESOLUTION = 1000

    def __init__(self, ui: UISettings, parent: Optional[qt.QWidget] = None) -> None:
        super().__init__("Scope controls", parent)
        self._ui = ui
        self._build_ui()

    def _build_ui(self) -> None:
        grid = qt.QGridLayout(self)
        grid.setColumnStretch(1, 1)

        # X scale (log)
        grid.addWidget(qt.QLabel("X scale (s):"), 0, 0)
        self._x_scale_slider = qt.QSlider(qt.Qt.Horizontal)
        self._x_scale_slider.setRange(0, self._SLIDER_RESOLUTION)
        self._x_scale_slider.setValue(
            log_slider_position(
                self._ui.window_seconds, self._ui.x_window_min, self._ui.x_window_max,
                self._SLIDER_RESOLUTION,
            )
        )
        self._x_scale_value = qt.QLabel(f"{self._ui.window_seconds:.2f}")
        self._x_scale_value.setStyleSheet("font-family: monospace;")
        self._x_scale_value.setMinimumWidth(60)
        grid.addWidget(self._x_scale_slider, 0, 1)
        grid.addWidget(self._x_scale_value, 0, 2)

        # X shift (linear, 0..x_shift_max)
        grid.addWidget(qt.QLabel("X shift (s):"), 1, 0)
        self._x_shift_slider = qt.QSlider(qt.Qt.Horizontal)
        self._x_shift_slider.setRange(0, self._SLIDER_RESOLUTION)
        self._x_shift_slider.setValue(0)
        self._x_shift_value = qt.QLabel("0.00")
        self._x_shift_value.setStyleSheet("font-family: monospace;")
        self._x_shift_value.setMinimumWidth(60)
        grid.addWidget(self._x_shift_slider, 1, 1)
        grid.addWidget(self._x_shift_value, 1, 2)

        # Y span (log)
        grid.addWidget(qt.QLabel("Y span (V):"), 2, 0)
        self._y_span_slider = qt.QSlider(qt.Qt.Horizontal)
        self._y_span_slider.setRange(0, self._SLIDER_RESOLUTION)
        default_span = self._ui.y_max - self._ui.y_min
        self._y_span_slider.setValue(
            log_slider_position(
                default_span, self._ui.y_span_min, self._ui.y_span_max,
                self._SLIDER_RESOLUTION,
            )
        )
        self._y_span_value = qt.QLabel(f"{default_span:.4f}")
        self._y_span_value.setStyleSheet("font-family: monospace;")
        self._y_span_value.setMinimumWidth(60)
        grid.addWidget(self._y_span_slider, 2, 1)
        grid.addWidget(self._y_span_value, 2, 2)

        # Channel checkboxes -- one row of toggles
        ch_label = qt.QLabel("Channels:")
        grid.addWidget(ch_label, 3, 0)
        ch_row = qt.QHBoxLayout()
        ch_row.setSpacing(8)
        self._channel_checkboxes: dict[int, qt.QCheckBox] = {}
        for ch_idx in sorted(self._ui.channel_labels):
            name = self._ui.channel_labels[ch_idx]
            color = self._ui.channel_colors.get(ch_idx, "#000000")
            cb = qt.QCheckBox(name)
            cb.setChecked(bool(self._ui.channel_enabled.get(ch_idx, False)))
            cb.setStyleSheet(f"color: {color}; font-weight: bold;")
            cb.toggled.connect(lambda _state: self.changed.emit())
            self._channel_checkboxes[ch_idx] = cb
            ch_row.addWidget(cb)
        ch_row.addStretch()
        ch_holder = qt.QWidget()
        ch_holder.setLayout(ch_row)
        grid.addWidget(ch_holder, 3, 1, 1, 2)

        # Wire slider signals
        self._x_scale_slider.valueChanged.connect(self._on_x_scale_changed)
        self._x_shift_slider.valueChanged.connect(self._on_x_shift_changed)
        self._y_span_slider.valueChanged.connect(self._on_y_span_changed)

    # ------------------------------------------------------------------
    # Slider callbacks
    # ------------------------------------------------------------------
    def _on_x_scale_changed(self, _pos: int) -> None:
        self._x_scale_value.setText(f"{self.x_scale_seconds():.2f}")
        # Changing X scale shrinks/extends the visible window; clamp X
        # shift if it would push the visible window beyond the ring
        # buffer length.
        self._clamp_x_shift()
        self.changed.emit()

    def _on_x_shift_changed(self, _pos: int) -> None:
        self._x_shift_value.setText(f"{self.x_shift_seconds():.2f}")
        self.changed.emit()

    def _on_y_span_changed(self, _pos: int) -> None:
        self._y_span_value.setText(f"{self.y_span_volts():.4f}")
        self.changed.emit()

    def _clamp_x_shift(self) -> None:
        """Ensure (X scale + X shift) <= ring depth so we can always satisfy the request."""
        max_shift = max(0.0, self._ui.x_shift_max - self.x_scale_seconds())
        current_shift = self.x_shift_seconds()
        if current_shift > max_shift:
            # Recompute slider position for the clamped shift.
            if max_shift <= 0.0:
                self._x_shift_slider.blockSignals(True)
                self._x_shift_slider.setValue(0)
                self._x_shift_slider.blockSignals(False)
                self._x_shift_value.setText("0.00")
            else:
                pos = int(round(max_shift / self._ui.x_shift_max * self._SLIDER_RESOLUTION))
                self._x_shift_slider.blockSignals(True)
                self._x_shift_slider.setValue(pos)
                self._x_shift_slider.blockSignals(False)
                self._x_shift_value.setText(f"{max_shift:.2f}")

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def x_scale_seconds(self) -> float:
        return log_slider_value(
            self._x_scale_slider.value(),
            self._ui.x_window_min,
            self._ui.x_window_max,
            self._SLIDER_RESOLUTION,
        )

    def x_shift_seconds(self) -> float:
        # Linear mapping for X shift since the natural unit (seconds in
        # the past) is itself an offset.
        pos = self._x_shift_slider.value()
        return self._ui.x_shift_max * pos / float(self._SLIDER_RESOLUTION)

    def y_span_volts(self) -> float:
        return log_slider_value(
            self._y_span_slider.value(),
            self._ui.y_span_min,
            self._ui.y_span_max,
            self._SLIDER_RESOLUTION,
        )

    def channel_enabled(self, ch_idx: int) -> bool:
        cb = self._channel_checkboxes.get(ch_idx)
        return bool(cb.isChecked()) if cb is not None else False


__all__ = [
    "ScopeControls",
    "downsample_for_display",
    "log_slider_value",
    "log_slider_position",
]
