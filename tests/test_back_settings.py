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
from pioner.shared.settings import BackSettings, parse_experiment_limits


def _settings_with_trigger(tmp_path: Path, value) -> str:
    """Clone the bundled defaults, override HardwareTrigger, return the path.

    ``value=None`` drops the field entirely (legacy file without it).
    """
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    daq = cfg["DaqSettings"]["DAQ"]
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
    """Clone the bundled defaults, set ``Scan.SampleRate`` to ``value``."""
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ExperimentSettings"]["Scan"]["SampleRate"] = value
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


# --- experiment limits (step 8 / P1-38) ------------------------------------

def test_default_limits():
    """Committed defaults: per-mode limit sets (fast 0..300, slow/iso 0..200)."""
    s = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    fast = s.limits_by_mode["fast"]
    assert fast.min_temp == 0.0 and fast.max_temp == 300.0
    assert fast.min_heat_rate == 100.0 and fast.max_heat_rate == 100000.0
    assert fast.min_cool_rate == 100.0 and fast.max_cool_rate == 100000.0
    slow = s.limits_by_mode["slow"]
    assert slow.max_temp == 200.0
    assert slow.min_heat_rate == 0.1 and slow.max_heat_rate == 60.0
    iso = s.limits_by_mode["iso"]
    assert iso.max_temp == 200.0
    assert iso.min_heat_rate is None and iso.max_heat_rate is None
    assert iso.min_cool_rate is None and iso.max_cool_rate is None


def test_limits_missing_block_defaults(tmp_path: Path):
    """A settings file without a Limits block falls back to the defaults."""
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ExperimentSettings"].pop("Limits", None)
    out = tmp_path / "settings.json"
    out.write_text(json.dumps(cfg))
    s = BackSettings(str(out))
    for mode in ("fast", "slow", "iso"):
        assert s.limits_by_mode[mode].min_temp == 0.0
        assert s.limits_by_mode[mode].max_temp == 300.0
    assert s.limits.min_temp == 0.0 and s.limits.max_temp == 300.0


def test_limits_flat_block_applies_to_all_modes(tmp_path: Path):
    """A flat (non per-mode) Limits block (back-compat) applies to every mode."""
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["ExperimentSettings"]["Limits"] = {
        "MinTemperature": 0, "MaxTemperature": 250, "MaxHeatRate": 5000,
    }
    out = tmp_path / "settings.json"
    out.write_text(json.dumps(cfg))
    s = BackSettings(str(out))
    for mode in ("fast", "slow", "iso"):
        assert s.limits_by_mode[mode].max_temp == 250.0
        assert s.limits_by_mode[mode].max_heat_rate == 5000.0
    # The scalar back-compat fallback mirrors the flat block.
    assert s.limits.max_temp == 250.0


def test_parse_experiment_limits_custom():
    lim = parse_experiment_limits({
        "MinTemperature": -10, "MaxTemperature": 250,
        "MinHeatRate": 1, "MaxHeatRate": 5000,
        "MinCoolRate": 2, "MaxCoolRate": 100,
    })
    assert lim.min_temp == -10.0 and lim.max_temp == 250.0
    assert lim.min_heat_rate == 1.0 and lim.max_heat_rate == 5000.0
    assert lim.min_cool_rate == 2.0 and lim.max_cool_rate == 100.0


def test_parse_experiment_limits_by_mode_partial():
    """A per-mode map: present modes parsed, absent modes get defaults."""
    from pioner.shared.settings import parse_experiment_limits_by_mode
    by_mode = parse_experiment_limits_by_mode({
        "fast": {"MaxTemperature": 300, "MinHeatRate": 100},
        "slow": {"MaxTemperature": 200, "MaxCoolRate": 60},
    })
    assert by_mode["fast"].max_temp == 300.0 and by_mode["fast"].min_heat_rate == 100.0
    assert by_mode["slow"].max_temp == 200.0 and by_mode["slow"].max_cool_rate == 60.0
    # "iso" absent -> built-in defaults.
    assert by_mode["iso"].max_temp == 300.0 and by_mode["iso"].max_heat_rate is None


def test_parse_experiment_limits_rejects_non_number():
    with pytest.raises(ValueError):
        parse_experiment_limits({"MaxTemperature": "hot"})


def test_front_settings_round_trips_limits_block():
    """A GUI save (get_exp_settings) must preserve the optional Limits block."""
    from pioner.shared.constants import LIMITS_FIELD
    from pioner.shared.settings import FrontSettings
    f = FrontSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    exp = f.get_exp_settings()
    assert LIMITS_FIELD in exp
    # Per-mode block is carried verbatim on save.
    assert exp[LIMITS_FIELD]["Fast"]["MaxTemperature"] == 300
    assert exp[LIMITS_FIELD]["Slow"]["MaxCoolRate"] == 60


def test_front_settings_omits_measured_reference_when_absent():
    """Default settings have no MeasuredReference -> GUI save must not inject it."""
    from pioner.shared.constants import MEASURED_REFERENCE_FIELD, MODULATION_FIELD
    from pioner.shared.settings import FrontSettings
    f = FrontSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    exp = f.get_exp_settings()
    assert MEASURED_REFERENCE_FIELD not in exp[MODULATION_FIELD]


def test_front_settings_round_trips_measured_reference(tmp_path: Path):
    """P1-34 regression: a GUI save must NOT strip Modulation.MeasuredReference
    (the backend reads the same file; dropping it silently disables the opt-in)."""
    from pioner.shared.constants import MEASURED_REFERENCE_FIELD, MODULATION_FIELD
    from pioner.shared.settings import BackSettings, FrontSettings

    data = json.loads(Path(DEFAULT_SETTINGS_FILE_REL_PATH).read_text())
    data["ExperimentSettings"][MODULATION_FIELD][MEASURED_REFERENCE_FIELD] = True
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(data))

    # GUI save preserves the flag verbatim.
    exp = FrontSettings(str(p)).get_exp_settings()
    assert exp[MODULATION_FIELD][MEASURED_REFERENCE_FIELD] is True
    # Backend actually consumes it.
    assert BackSettings(str(p)).modulation.use_measured_reference is True


# --- CamelCase config keys/values (capitalized in settings.json) -----------

def test_rate_map_accepts_capitalized_keys(tmp_path: Path):
    """Config may capitalize the mode keys; the internal map stays lowercase."""
    s = BackSettings(_settings_with_rate(tmp_path, {"Default": 1000, "Fast": 4000}))
    assert s.sample_rate_by_mode == {
        "default": 1000, "fast": 4000, "slow": 1000, "iso": 1000,
    }


def test_limits_accepts_capitalized_mode_keys():
    from pioner.shared.settings import parse_experiment_limits_by_mode
    by_mode = parse_experiment_limits_by_mode({
        "Fast": {"MaxTemperature": 300}, "Slow": {"MaxTemperature": 200},
    })
    assert by_mode["fast"].max_temp == 300.0
    assert by_mode["slow"].max_temp == 200.0
    assert by_mode["iso"].max_temp == 300.0  # absent -> defaults


def test_chip_presence_strategy_camelcase():
    from pioner.shared.settings import parse_chip_presence_config
    assert parse_chip_presence_config({"Strategy": "Band"}).strategy == "band"
    assert parse_chip_presence_config({"Strategy": "AbsLevel"}).strategy == "abs_level"
    assert parse_chip_presence_config({"Strategy": "Variance"}).strategy == "variance"
    with pytest.raises(ValueError):
        parse_chip_presence_config({"Strategy": "Nope"})


def test_acquisition_mode_camelcase(tmp_path: Path):
    """``Persistent`` / ``PerExperiment`` normalise to the internal canonical."""
    with open(DEFAULT_SETTINGS_FILE_REL_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["AcquisitionMode"] = "PerExperiment"
    out = tmp_path / "settings.json"
    out.write_text(json.dumps(cfg))
    assert BackSettings(str(out)).acquisition_mode == "per_experiment"
    # The committed default uses the capitalized "Persistent".
    assert BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH).acquisition_mode == "persistent"
