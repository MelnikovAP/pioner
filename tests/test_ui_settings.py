"""Tests for ``UISettings`` -- the front-end UI parameter loader.

These tests run without a Qt application; the loader is pure-Python
JSON parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pioner.shared.constants import DEFAULT_UI_SETTINGS_FILE_REL_PATH
from pioner.shared.settings import UISettings


class TestDefaults:
    """Loading the committed default file populates every documented field."""

    def test_loads_packaged_defaults(self):
        ui = UISettings(DEFAULT_UI_SETTINGS_FILE_REL_PATH)
        assert ui.window_seconds > 0
        assert ui.y_min < ui.y_max
        assert ui.max_plot_points > 0
        assert ui.refresh_interval_ms > 0
        assert len(ui.channel_indices) > 0
        assert len(ui.channel_labels) >= 6
        assert len(ui.channel_colors) >= 6
        assert len(ui.channel_enabled) >= 6
        assert ui.ring_max_seconds > ui.window_seconds  # ring must cover window
        assert ui.x_window_min < ui.x_window_max
        assert ui.y_span_min < ui.y_span_max

    def test_falls_back_when_file_missing(self):
        """No file at the path -> defaults, no exception."""
        ui = UISettings("/tmp/does-not-exist-pioner.json")
        assert ui.window_seconds == UISettings._DEFAULTS["window_seconds"]
        assert ui.channel_labels == UISettings._DEFAULTS["channel_labels"]


class TestUserOverrides:
    """JSON file with partial overrides keeps the rest as defaults."""

    def test_partial_override(self, tmp_path: Path):
        cfg = tmp_path / "custom.json"
        cfg.write_text(json.dumps({
            "Plot": {"WindowSeconds": 0.5, "YMin": -0.1, "YMax": 0.1},
        }))
        ui = UISettings(str(cfg))
        assert ui.window_seconds == pytest.approx(0.5)
        assert ui.y_min == pytest.approx(-0.1)
        assert ui.y_max == pytest.approx(0.1)
        # Untouched fields keep defaults.
        assert ui.refresh_interval_ms == UISettings._DEFAULTS["refresh_interval_ms"]
        assert ui.channel_labels == UISettings._DEFAULTS["channel_labels"]

    def test_full_override(self, tmp_path: Path):
        cfg = tmp_path / "full.json"
        cfg.write_text(json.dumps({
            "Plot": {
                "WindowSeconds": 0.5,
                "YMin": -1.0,
                "YMax": 1.0,
                "MaxPoints": 500,
                "RefreshIntervalMs": 100,
                "ChannelIndices": [0, 1],
                "ChannelLabels": {"0": "A", "1": "B"},
                "ChannelColors": {"0": "#ff0000", "1": "#00ff00"},
                "ChannelEnabled": {"0": True, "1": False},
            },
            "Ring": {"MaxSeconds": 2.0},
            "Demod": {"WindowPeriods": 10},
            "DemoAO": {
                "DurationSeconds": 8.0,
                "ModulationFrequency": 100.0,
                "ModulationAmplitudeV": 0.5,
                "RampPeakV": 1.0,
            },
            "Sliders": {
                "XWindowMinSeconds": 0.01,
                "XWindowMaxSeconds": 100.0,
                "XShiftMaxSeconds": 50.0,
                "YSpanMinV": 0.0001,
                "YSpanMaxV": 10.0,
            },
        }))
        ui = UISettings(str(cfg))
        assert ui.window_seconds == pytest.approx(0.5)
        assert ui.max_plot_points == 500
        assert ui.channel_labels[0] == "A"
        assert ui.channel_labels[1] == "B"
        # Missing channel indices backfill from defaults (so the UI
        # always has labels/colors for every channel).
        assert 4 in ui.channel_labels
        assert ui.ring_max_seconds == pytest.approx(2.0)
        assert ui.demo_modulation_frequency == pytest.approx(100.0)
        assert ui.x_shift_max == pytest.approx(50.0)


class TestCoercion:
    """Permissive coercion at the boundary -- don't crash on a typo."""

    def test_bad_channel_key_dropped(self, tmp_path: Path):
        cfg = tmp_path / "bad.json"
        cfg.write_text(json.dumps({
            "Plot": {"ChannelLabels": {"0": "Uref", "not_a_number": "garbage", "1": "Umod"}},
        }))
        ui = UISettings(str(cfg))
        # "not_a_number" silently dropped; valid keys preserved; missing
        # ones backfilled from defaults.
        assert ui.channel_labels[0] == "Uref"
        assert ui.channel_labels[1] == "Umod"
        assert "not_a_number" not in ui.channel_labels
        assert 4 in ui.channel_labels  # backfilled

    def test_channel_indices_coerce_to_tuple_of_ints(self, tmp_path: Path):
        cfg = tmp_path / "idx.json"
        cfg.write_text(json.dumps({
            "Plot": {"ChannelIndices": [0, "1", 4]},
        }))
        ui = UISettings(str(cfg))
        assert ui.channel_indices == (0, 1, 4)
