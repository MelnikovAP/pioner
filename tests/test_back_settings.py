"""Tests for ``BackSettings`` DAQ-parameter parsing.

Focused on the settings-driven ``hardware_trigger`` flag (todo P0-5): the
bundled defaults keep it off, and an explicit ``HardwareTrigger`` boolean in
the DAQ block round-trips into ``daq_params.hardware_trigger``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH
from pioner.shared.settings import BackSettings


def _settings_with_trigger(tmp_path: Path, value) -> str:
    """Clone the bundled defaults, override HardwareTrigger, return the path.

    ``value=None`` drops the field entirely (legacy file without it).
    """
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    daq = cfg["DAQ settings"]["DAQ"]
    if value is None:
        daq.pop("HardwareTrigger", None)
    else:
        daq["HardwareTrigger"] = value
    out = tmp_path / "settings.json"
    out.write_text(json.dumps(cfg))
    return str(out)


def test_default_settings_hardware_trigger_off():
    """The committed defaults must keep the trigger off."""
    settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    assert settings.daq_params.hardware_trigger is False


def test_hardware_trigger_true_round_trips(tmp_path: Path):
    settings = BackSettings(_settings_with_trigger(tmp_path, True))
    assert settings.daq_params.hardware_trigger is True


def test_hardware_trigger_false_round_trips(tmp_path: Path):
    settings = BackSettings(_settings_with_trigger(tmp_path, False))
    assert settings.daq_params.hardware_trigger is False


def test_hardware_trigger_missing_defaults_off(tmp_path: Path):
    """A legacy file without the field keeps the DaqParams default (False)."""
    settings = BackSettings(_settings_with_trigger(tmp_path, None))
    assert settings.daq_params.hardware_trigger is False


# --- per-mode sample rate (P1-31) ------------------------------------------

def _settings_with_rate(tmp_path: Path, value) -> str:
    """Clone the bundled defaults, set ``Scan.Sample rate`` to ``value``."""
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["Experiment settings"]["Scan"]["Sample rate"] = value
    out = tmp_path / "settings.json"
    out.write_text(json.dumps(cfg))
    return str(out)


def test_default_per_mode_rates():
    """The committed defaults split fast (20 kHz) from slow/iso/monitor (2 kHz)."""
    settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    assert settings.sample_rate_by_mode == {
        "default": 2000, "fast": 20000, "slow": 2000, "iso": 2000,
    }
    # Active rate starts at the idle-monitor default; AO == AI.
    assert settings.ai_params.sample_rate == 2000
    assert settings.ao_params.sample_rate == 2000


def test_bare_int_rate_back_compat(tmp_path: Path):
    """A scalar rate (legacy form) applies to every mode."""
    settings = BackSettings(_settings_with_rate(tmp_path, 5000))
    assert settings.sample_rate_by_mode == {
        "default": 5000, "fast": 5000, "slow": 5000, "iso": 5000,
    }
    assert settings.ai_params.sample_rate == 5000


def test_rate_map_partial_falls_back_to_default(tmp_path: Path):
    """Missing per-mode keys inherit the ``default`` rate."""
    settings = BackSettings(_settings_with_rate(tmp_path, {"default": 1000, "fast": 4000}))
    assert settings.sample_rate_by_mode == {
        "default": 1000, "fast": 4000, "slow": 1000, "iso": 1000,
    }


def test_rate_map_without_default_is_invalid(tmp_path: Path):
    """A map lacking the required ``default`` key is rejected."""
    with pytest.raises(ValueError):
        BackSettings(_settings_with_rate(tmp_path, {"fast": 20000}))


def test_rate_bool_is_invalid(tmp_path: Path):
    """``true`` must not be accepted as a sample rate (bool is an int subclass)."""
    with pytest.raises(ValueError):
        BackSettings(_settings_with_rate(tmp_path, True))
