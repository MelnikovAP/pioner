import json
from pathlib import Path

from pioner_app.paths import PROJECT_ROOT


BASE_DIR = PROJECT_ROOT
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
USER_CONFIG_PATH = BASE_DIR / "config.user.json"


def _deep_update(base, override):
    """Stub for `deep_update`."""
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


class Config:

    def __init__(self, path=None, user_path=None):
        """Stub docstring."""
        self.path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        self.user_path = Path(user_path) if user_path is not None else USER_CONFIG_PATH

        if not self.path.exists():
            raise FileNotFoundError(f"Config file not found: {self.path}")

        with open(self.path, encoding="utf-8") as f:
            self.default_data = json.load(f)

        self.data = json.loads(json.dumps(self.default_data))

        if self.user_path.exists():
            with open(self.user_path, encoding="utf-8") as f:
                user_data = json.load(f)
            self.data = _deep_update(self.data, user_data)

        self._parse()

    def _resolve_path(self, value):
        """Stub for `resolve_path`."""
        if not value:
            return value
        candidate = Path(value)
        if candidate.is_absolute():
            return str(candidate)
        return str((BASE_DIR / candidate).resolve())

    def _parse(self):
        """Stub for `parse`."""
        daq = self.data["DAQ settings"]["DAQ"]
        ai = self.data["DAQ settings"]["AI"]
        ao = self.data["DAQ settings"]["AO"]
        exp = self.data["Experiment settings"]
        server = self.data.get("Server settings", {})
        tango = server.get("Tango", {})
        http = server.get("HTTP", {})

        self.interface_type = daq["InterfaceType"]
        self.connection_code = daq["ConnectionCode"]
        self.connection_mode = daq.get("ConnectionMode", "direct")

        self.ai_low = ai["LowChannel"]
        self.ai_high = ai["HighChannel"]
        self.ai_range = ai["RangeId"]
        self.ai_input_mode = ai["InputMode"]

        self.ao_low = ao["LowChannel"]
        self.ao_high = ao["HighChannel"]
        self.ao_range = ao["RangeId"]

        self.sample_rate = exp["Scan"]["Sample rate"]
        self.ai_names = exp["AI channels"]

        self.calibration_path = self._resolve_path(exp["Paths"]["Calibration path"])
        self.data_path = self._resolve_path(exp["Paths"].get("Data path", ""))

        self.mod_freq = exp["Modulation"]["Frequency"]
        self.mod_amp = exp["Modulation"]["Amplitude"]
        self.mod_offset = exp["Modulation"]["Offset"]

        gains = exp.get("Input gains", {})
        default_ranges = {"Uref": 5, "Umod": 5, "Utpl": 5, "Uhtr": 5, "Uaux": 5}
        default_auto = {"Uref": True, "Umod": True, "Utpl": True, "Uhtr": True, "Uaux": True}
        self.input_gain_ranges = {**default_ranges, **gains.get("Ranges", {})}
        self.input_gain_auto = {**default_auto, **gains.get("Auto gain", {})}

        self.tango_host = tango.get("Tango host", "")
        self.device_proxy = tango.get("Device proxy", "")
        self.http_host = http.get("HTTP host", "")

        ui = self.data.get("UI", {})
        self.ui_language = ui.get("Language", "en")

    def build_runtime_config(self, *, connection_mode, tango_host, device_proxy, http_host,
                             calibration_path, data_path, sample_rate, mod_freq, mod_amp, mod_offset,
                             input_gain_ranges=None, input_gain_auto=None):
        """Stub for `build_runtime_config`."""
        config = json.loads(json.dumps(self.default_data))
        config["DAQ settings"]["DAQ"]["ConnectionMode"] = connection_mode
        config["Server settings"]["Tango"]["Tango host"] = tango_host
        config["Server settings"]["Tango"]["Device proxy"] = device_proxy
        config["Server settings"]["HTTP"]["HTTP host"] = http_host
        config["Experiment settings"]["Paths"]["Calibration path"] = calibration_path
        config["Experiment settings"]["Paths"]["Data path"] = data_path
        config["Experiment settings"]["Scan"]["Sample rate"] = sample_rate
        config["Experiment settings"]["Modulation"]["Frequency"] = mod_freq
        config["Experiment settings"]["Modulation"]["Amplitude"] = mod_amp
        config["Experiment settings"]["Modulation"]["Offset"] = mod_offset
        config["Experiment settings"]["Input gains"] = {
            "Ranges": input_gain_ranges or dict(getattr(self, "input_gain_ranges", {})),
            "Auto gain": input_gain_auto or dict(getattr(self, "input_gain_auto", {})),
        }
        config.setdefault("UI", {})["Language"] = getattr(self, "ui_language", "en")
        return config

    def save_user_config(self, config):
        """Stub for `save_user_config`."""
        with open(self.user_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        self.data = config
        self._parse()

    def reload(self):
        """Stub for `reload`."""
        self.__init__(self.path, self.user_path)

    def reset_user_config(self):
        """Stub for `reset_user_config`."""
        if self.user_path.exists():
            self.user_path.unlink()
        self.reload()

    def save_ui_language(self, language):
        """Stub for `save_ui_language`."""
        config = json.loads(json.dumps(self.data))
        config.setdefault("UI", {})["Language"] = language
        self.save_user_config(config)


settings = Config()

import json
import os 

try:
    from ai_device import AiParams
    from ao_device import AoParams
    from daq_controller import DaqParams
except:
    pass

from pioner_app.core.utils import is_int_or_raise, list_bitwise_or
from pioner_app.core.constants import *
