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
