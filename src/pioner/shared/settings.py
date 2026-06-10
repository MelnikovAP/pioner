"""JSON-backed configuration parsers for the back-end and the front-end.

Two settings flavours live in the same file because they share most of the
schema:

* :class:`BackSettings` — used by the Tango device server. It needs DAQ
  params (``DaqParams`` / ``AiParams`` / ``AoParams``) which themselves
  depend on ``uldaq`` and therefore are imported lazily.
* :class:`FrontSettings` — used by the Qt GUI; it does not need any DAQ
  bindings, only Tango / HTTP host strings and modulation defaults.
"""

import json
import logging
import os
from dataclasses import dataclass

# DAQ parameter classes are needed only by ``BackSettings``. Importing them
# requires (mock) ``uldaq``, so we tolerate failures silently and re-raise
# something more useful at instantiation time.
try:
    from pioner.back.ai_device import AiParams
    from pioner.back.ao_device import AoParams
    from pioner.back.daq_device import DaqParams
    _DAQ_PARAMS_AVAILABLE = True
    _DAQ_PARAMS_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on host
    _DAQ_PARAMS_AVAILABLE = False
    _DAQ_PARAMS_IMPORT_ERROR = exc
    logging.getLogger(__name__).debug(
        "DAQ params not importable (%s); BackSettings will fail until uldaq is installed.",
        exc,
    )

from pioner.shared.utils import is_int_or_raise, list_bitwise_or
from pioner.shared.constants import *  # noqa: F401,F403 - intentional re-export of field names


#: Per-mode keys recognised in the ``Scan.SampleRate`` map (besides
#: ``default``, which is the idle-monitor rate and the fallback for any
#: mode key that is absent). See P1-31.
SAMPLE_RATE_MODE_KEYS = ("fast", "slow", "iso")


def resolve_sample_rate_map(value) -> dict:
    """Normalise the ``Scan.SampleRate`` field into a per-mode rate map.

    Accepts either a bare int (back-compat: every mode uses the same rate) or
    a dict ``{"Default": int, "Fast": int, "Slow": int, "Iso": int}`` where
    ``Default`` is required and any missing per-mode key falls back to it.
    Keys are matched **case-insensitively**, so the config may capitalize the
    mode names while the returned map stays lowercase (the internal canonical).

    Returns ``{"default", "fast", "slow", "iso"}`` -> int. Raises ``ValueError``
    / ``TypeError`` on malformed input so the caller can flag the field.
    """
    def _as_int(v) -> int:
        # bool is an int subclass; reject it explicitly so ``true`` is invalid.
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(f"sample rate must be an int, got {v!r}")
        return int(v)

    if isinstance(value, bool):
        raise ValueError("sample rate must be an int or a map, not a bool")
    if isinstance(value, int):
        rate = int(value)
        return {"default": rate, **{k: rate for k in SAMPLE_RATE_MODE_KEYS}}
    if isinstance(value, dict):
        # Case-insensitive: accept Capitalized config keys (Default/Fast/...),
        # return the lowercase internal map. Last value wins on case collisions.
        lowered = {str(k).lower(): v for k, v in value.items()}
        if "default" not in lowered:
            raise ValueError("sample rate map needs a 'Default' key")
        default = _as_int(lowered["default"])
        out = {"default": default}
        for key in SAMPLE_RATE_MODE_KEYS:
            out[key] = _as_int(lowered[key]) if key in lowered else default
        return out
    raise TypeError(f"sample rate must be int or dict, got {type(value).__name__}")


#: Per-mode keys recognised in the ``Limits`` block (besides a flat back-compat
#: block that applies to every mode). Mirrors ``SAMPLE_RATE_MODE_KEYS``.
LIMITS_MODE_KEYS = ("fast", "slow", "iso")


@dataclass
class ExperimentLimits:
    """Operator safety limits for experiment programs (TODO step 8 / P1-38).

    ``min_temp`` / ``max_temp`` (deg C) are the heating-only allowed range
    (no cryostat). ``min_heat_rate`` / ``max_heat_rate`` and ``min_cool_rate`` /
    ``max_cool_rate`` (K/s, magnitude) bound the per-segment ramp rates; ``None``
    on any bound disables that single check (the achievable cool rate is
    hardware-dependent -- fill it in from the bench, P1-38).
    """

    min_temp: float = 0.0
    max_temp: float = 300.0
    min_heat_rate: float | None = None
    max_heat_rate: float | None = None
    min_cool_rate: float | None = None
    max_cool_rate: float | None = None


def parse_experiment_limits(value: dict | None) -> ExperimentLimits:
    """Build :class:`ExperimentLimits` from a single (flat) ``Limits`` block.

    Missing block / keys fall back to the defaults (back-compat). Keys:
    ``MinTemperature``, ``MaxTemperature``, ``MinHeatRate``,
    ``MaxHeatRate``, ``MinCoolRate``, ``MaxCoolRate``.
    """
    d = value or {}

    def _opt(key: str) -> float | None:
        v = d.get(key)
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"Limits.{key} must be a number, got {v!r}")
        return float(v)

    def _req(key: str, default: float) -> float:
        v = _opt(key)
        return default if v is None else v

    return ExperimentLimits(
        min_temp=_req("MinTemperature", 0.0),
        max_temp=_req("MaxTemperature", 300.0),
        min_heat_rate=_opt("MinHeatRate"),
        max_heat_rate=_opt("MaxHeatRate"),
        min_cool_rate=_opt("MinCoolRate"),
        max_cool_rate=_opt("MaxCoolRate"),
    )


def parse_experiment_limits_by_mode(value: dict | None) -> dict:
    """Build a ``{mode: ExperimentLimits}`` map from the optional ``Limits`` block.

    Two accepted shapes (mirrors the ``SampleRate`` field, P1-31):

    * **Per-mode map** -- a dict containing any of the mode keys
      (``"Fast"`` / ``"Slow"`` / ``"Iso"``, matched case-insensitively). Each
      present mode's sub-block is parsed with :func:`parse_experiment_limits`;
      a mode key that is absent falls back to the built-in defaults.
    * **Flat block** (back-compat) -- a dict with the limit keys directly
      (``"MinTemperature"`` ...). The same limits apply to every mode.
    * **Absent** (``None`` / ``{}``) -> built-in defaults for every mode.

    Returns ``{"fast", "slow", "iso"}`` -> :class:`ExperimentLimits`.
    """
    if value is None:
        return {k: ExperimentLimits() for k in LIMITS_MODE_KEYS}
    if not isinstance(value, dict):
        raise TypeError(
            f"Limits must be a map, got {type(value).__name__}"
        )
    # Case-insensitive: accept Capitalized mode keys (Fast/Slow/Iso), return the
    # lowercase internal map.
    lowered = {str(k).lower(): v for k, v in value.items()}
    if any(k in lowered for k in LIMITS_MODE_KEYS):
        # Per-mode map: parse each present mode; absent modes get defaults.
        return {
            k: parse_experiment_limits(lowered[k]) if k in lowered else ExperimentLimits()
            for k in LIMITS_MODE_KEYS
        }
    # Flat block (back-compat): one shared limit set for every mode.
    shared = parse_experiment_limits(value)
    return {k: shared for k in LIMITS_MODE_KEYS}


#: Candidate chip-presence detection strategies (P1-36). All are read-only and
#: passive (they inspect the live AI window, never drive AO). The discriminating
#: channel + threshold must be picked on the bench (chip in vs out); see
#: ``back/chip_presence.py``.
CHIP_PRESENCE_STRATEGIES = ("band", "abs_level", "variance")

#: Map a config Strategy spelling (CamelCase ``Band`` / ``AbsLevel`` /
#: ``Variance`` or the internal lowercase form) to the internal canonical. Keyed
#: by the value lowercased with underscores stripped, so both spellings resolve.
_CHIP_PRESENCE_STRATEGY_BY_NORM = {
    "band": "band", "abslevel": "abs_level", "variance": "variance",
}


def _normalize_chip_presence_strategy(value) -> str:
    """Normalise a config Strategy value to the internal lowercase canonical.

    Accepts CamelCase (``Band`` / ``AbsLevel`` / ``Variance``) or the internal
    form. Unknown values pass through unchanged so the caller rejects them.
    """
    norm = str(value).replace("_", "").lower()
    return _CHIP_PRESENCE_STRATEGY_BY_NORM.get(norm, str(value))


#: Map an AcquisitionMode spelling (CamelCase ``Persistent`` / ``PerExperiment``
#: or the internal lowercase form) to the internal canonical.
_ACQUISITION_MODE_BY_NORM = {
    "persistent": "persistent", "perexperiment": "per_experiment",
}


def _normalize_acquisition_mode(value) -> str:
    """Normalise the AcquisitionMode value to the internal lowercase canonical.

    Accepts ``Persistent`` / ``PerExperiment`` (or the internal form). Unknown
    values pass through; :meth:`AcquisitionMode.from_string` then falls back.
    """
    if value is None:
        return ACQUISITION_MODE_DEFAULT
    norm = str(value).replace("_", "").lower()
    return _ACQUISITION_MODE_BY_NORM.get(norm, str(value))


@dataclass
class ChipPresenceConfig:
    """Config for read-only chip-presence detection (P1-36).

    ``enabled`` defaults to ``False`` so detection never gates the experiment
    lifecycle until a strategy + threshold has been validated on real hardware
    (an unvalidated threshold would falsely block valid runs). ``channel`` is an
    AI channel index (default 4 = ``Utpl``); the thresholds belong to whichever
    ``strategy`` is active. Defaults are deliberately permissive.
    """

    enabled: bool = False
    strategy: str = "band"
    channel: int = 4          # UTPL_AI (thermopile); see shared/channels.py
    band_lo: float = -10.0
    band_hi: float = 10.0
    max_abs: float = 9.5
    max_std: float = 1.0


def parse_chip_presence_config(value: dict | None) -> ChipPresenceConfig:
    """Build :class:`ChipPresenceConfig` from the optional ``ChipPresence`` block.

    Missing block / keys fall back to the defaults (detection disabled). Keys:
    ``Enabled``, ``Strategy``, ``Channel``, ``BandLow``, ``BandHigh``,
    ``MaxAbs``, ``MaxStd``.
    """
    d = value or {}
    defaults = ChipPresenceConfig()

    def _num(key: str, default: float) -> float:
        v = d.get(key)
        if v is None:
            return default
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"ChipPresence.{key} must be a number, got {v!r}")
        return float(v)

    strategy_raw = d.get("Strategy", defaults.strategy)
    strategy = _normalize_chip_presence_strategy(strategy_raw)
    if strategy not in CHIP_PRESENCE_STRATEGIES:
        raise ValueError(
            f"ChipPresence.Strategy must be one of {CHIP_PRESENCE_STRATEGIES}, got {strategy_raw!r}"
        )
    channel = d.get("Channel", defaults.channel)
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ValueError(f"ChipPresence.Channel must be an int, got {channel!r}")

    return ChipPresenceConfig(
        enabled=bool(d.get("Enabled", defaults.enabled)),
        strategy=str(strategy),
        channel=int(channel),
        band_lo=_num("BandLow", defaults.band_lo),
        band_hi=_num("BandHigh", defaults.band_hi),
        max_abs=_num("MaxAbs", defaults.max_abs),
        max_std=_num("MaxStd", defaults.max_std),
    )


class JsonReader:
    """Reads a JSON configuration file."""

    def __init__(self, path: str):
        """Initializes dictionary.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if file doesn't exist or has invalid extension or is empty.
        """
        self._json = dict()
        if not os.path.exists(path):
            raise ValueError(f"Settings file '{path}' does not exist.")
        ext = os.path.splitext(path)[-1].lower().lstrip(".")
        if ext != JSON_EXTENSION:
            raise ValueError(
                f"Settings file '{path}' must have '.{JSON_EXTENSION}' extension."
            )
        with open(path, 'r', encoding="utf-8") as f:
            self._json = json.load(f)
        if not self._json:
            raise ValueError(f"Settings file '{path}' is empty.")

    def json(self):
        """Provides access to the read dictionary."""
        return self._json

class BackSettings:
    """Parses configuration file with all necessary acquisition parameters.

    Note: only the ``DaqSettings`` block and ``ExperimentSettings.Scan`` /
    ``ExperimentSettings.Modulation`` are consumed here. The
    ``ExperimentSettings.Paths`` block (``CalibrationPath``, ``DataPath``)
    and the ``ServerSettings`` block are read by :class:`FrontSettings` only.
    The Tango back-end uses the hardcoded ``CALIBRATION_FILE_REL_PATH`` /
    ``RAW_DATA_FOLDER_REL_PATH`` constants.
    """

    def __init__(self, path: str):
        """Initializes dictionary and checks that all needed fields exist.

        After correct parsing it is possible to obtain DaqParams, AiParams and AoParams.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if any field doesn't exist.
        """
        if not _DAQ_PARAMS_AVAILABLE:
            raise RuntimeError(
                "BackSettings needs the DAQ params modules (pioner.back.ai_device etc.); "
                f"failed to import them: {_DAQ_PARAMS_IMPORT_ERROR}."
            )

        json_dict = JsonReader(path).json()
        if DAQ_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(DAQ_SETTINGS_FIELD))
        else:
            self._daq_settings_dict = json_dict[DAQ_SETTINGS_FIELD]
            for field in [DAQ_FIELD, AI_FIELD, AO_FIELD]:
                if field not in self._daq_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))
        
        if EXPERIMENT_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(EXPERIMENT_SETTINGS_FIELD))
        else:
            self._exp_settings_dict = json_dict[EXPERIMENT_SETTINGS_FIELD]
            for field in [PATHS_FIELD, SCAN_FIELD, MODULATION_FIELD]:
                if field not in self._exp_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))

        self._invalid_fields = []
        # only in that order
        self.parse_daq_params()
        self.parse_ai_params()
        self.parse_ao_params()
        self.parse_modulation()
        self.parse_acquisition_mode(json_dict)
        self.parse_limits()
        self.parse_chip_presence()
        self.check_invalid_fields()

    def parse_acquisition_mode(self, json_dict: dict) -> None:
        """Pull the top-level ``AcquisitionMode`` field, default if missing.

        Valid values are ``"persistent"`` (default) and ``"per_experiment"``.
        Unknown values are accepted at this layer (the AIProvider factory
        validates and falls back to ``persistent``); the field is purely
        a string here.
        """
        value = json_dict.get(ACQUISITION_MODE_FIELD, ACQUISITION_MODE_DEFAULT)
        self.acquisition_mode = _normalize_acquisition_mode(value)

    def parse_modulation(self) -> None:
        """Pull AC modulation defaults (Hz, V) into ``self.modulation``."""
        from pioner.shared.modulation import ModulationParams  # avoid cycle

        mod = self._exp_settings_dict.get(MODULATION_FIELD, {})
        self.modulation = ModulationParams(
            frequency=float(mod.get(FREQUENCY_FIELD, 0.0)),
            amplitude=float(mod.get(AMPLITUDE_FIELD, 0.0)),
            offset=float(mod.get(OFFSET_FIELD, 0.0)),
        )

    def parse_limits(self) -> None:
        """Pull operator safety limits from the optional ``Limits`` block.

        Supports a per-mode map (``{"fast": {...}, "slow": {...}, "iso": {...}}``)
        or a single flat block applied to every mode (back-compat). Absent block
        -> defaults (min 0 / max 300 C, no rate cap). See
        :func:`parse_experiment_limits_by_mode` and TODO step 8 / P1-38.

        Exposes ``limits_by_mode`` (the per-mode map consumed at arm) and the
        scalar ``limits`` (back-compat fallback for an unknown mode name: the
        flat block when one was given, else built-in defaults).
        """
        raw = self._exp_settings_dict.get(LIMITS_FIELD)
        self.limits_by_mode = parse_experiment_limits_by_mode(raw)
        is_flat = isinstance(raw, dict) and not any(
            k in raw for k in LIMITS_MODE_KEYS
        )
        self.limits = parse_experiment_limits(raw) if is_flat else ExperimentLimits()

    def parse_chip_presence(self) -> None:
        """Pull the optional chip-presence block (P1-36); absent -> disabled."""
        self.chip_presence = parse_chip_presence_config(
            self._exp_settings_dict.get(CHIP_PRESENCE_FIELD)
        )

    def parse_daq_params(self):
        """Parses all necessary DAQ parameters and fills DaqParams instance."""
        self.daq_params = DaqParams()
        daq_dict = self._daq_settings_dict[DAQ_FIELD]

        if INTERFACE_TYPE_FIELD in daq_dict:
            interface_types = daq_dict[INTERFACE_TYPE_FIELD]
            if isinstance(interface_types, list):
                self.daq_params.interface_type = list_bitwise_or(interface_types)
            elif is_int_or_raise(interface_types):
                self.daq_params.interface_type = int(interface_types)
        else:
            self._invalid_fields.append(INTERFACE_TYPE_FIELD)

        if CONNECTION_CODE_FIELD in daq_dict:
            connection_code = daq_dict[CONNECTION_CODE_FIELD]
            if is_int_or_raise(connection_code):
                self.daq_params.connection_code = int(connection_code)
        else:
            self._invalid_fields.append(CONNECTION_CODE_FIELD)

        # Optional: AO/AI hardware-trigger sync (todo P0-5). Absent -> keep the
        # DaqParams default (False); present -> coerce to bool. Not added to
        # ``_invalid_fields`` so existing settings files stay valid.
        if HARDWARE_TRIGGER_FIELD in daq_dict:
            self.daq_params.hardware_trigger = bool(daq_dict[HARDWARE_TRIGGER_FIELD])

    def parse_ai_params(self):
        """Parses all necessary analog-input parameters and fills AiParams instance."""
        self.ai_params = AiParams()
        ai_dict = self._daq_settings_dict[AI_FIELD]
        scan_dict = self._exp_settings_dict[SCAN_FIELD]

        if SAMPLE_RATE_FIELD in scan_dict:
            try:
                rate_map = resolve_sample_rate_map(scan_dict[SAMPLE_RATE_FIELD])
            except (ValueError, TypeError):
                if SAMPLE_RATE_FIELD not in self._invalid_fields:
                    self._invalid_fields.append(SAMPLE_RATE_FIELD)
            else:
                # Per-mode rate map (P1-31); active rate starts at the
                # idle-monitor ``default`` and is switched per mode at arm.
                self.sample_rate_by_mode = rate_map
                self.ai_params.sample_rate = rate_map["default"]
        else:
            if SAMPLE_RATE_FIELD not in self._invalid_fields:
                self._invalid_fields.append(SAMPLE_RATE_FIELD)

        if RANGE_ID_FIELD in ai_dict:
            range_id = ai_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self.ai_params.range_id = int(range_id)
        else:
            self._invalid_fields.append(RANGE_ID_FIELD)

        if LOW_CHANNEL_FIELD in ai_dict:
            low_channel = ai_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self.ai_params.low_channel = int(low_channel)
        else:
            self._invalid_fields.append(LOW_CHANNEL_FIELD)

        if HIGH_CHANNEL_FIELD in ai_dict:
            high_channel = ai_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self.ai_params.high_channel = int(high_channel)
        else:
            self._invalid_fields.append(HIGH_CHANNEL_FIELD)

        if INPUT_MODE_FIELD in ai_dict:
            input_mode = ai_dict[INPUT_MODE_FIELD]
            if is_int_or_raise(input_mode):
                self.ai_params.input_mode = int(input_mode)
        else:
            self._invalid_fields.append(INPUT_MODE_FIELD)

        if SCAN_FLAGS_FIELD in ai_dict:
            scan_flags = ai_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                self.ai_params.scan_flags = list_bitwise_or(scan_flags)
            elif is_int_or_raise(scan_flags):
                self.ai_params.scan_flags = int(scan_flags)
        else:
            self._invalid_fields.append(SCAN_FLAGS_FIELD)

    def parse_ao_params(self):
        """Parses all necessary analog-output parameters and fills AoParams instance."""
        self.ao_params = AoParams()
        ao_dict = self._daq_settings_dict[AO_FIELD]
        scan_dict = self._exp_settings_dict[SCAN_FIELD]

        if SAMPLE_RATE_FIELD in scan_dict:
            try:
                rate_map = resolve_sample_rate_map(scan_dict[SAMPLE_RATE_FIELD])
            except (ValueError, TypeError):
                if SAMPLE_RATE_FIELD not in self._invalid_fields:
                    self._invalid_fields.append(SAMPLE_RATE_FIELD)
            else:
                # AO shares the AI rate (README invariant); same map.
                self.sample_rate_by_mode = rate_map
                self.ao_params.sample_rate = rate_map["default"]
        else:
            if SAMPLE_RATE_FIELD not in self._invalid_fields:
                self._invalid_fields.append(SAMPLE_RATE_FIELD)

        if RANGE_ID_FIELD in ao_dict:
            range_id = ao_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self.ao_params.range_id = int(range_id)
        else:
            self._invalid_fields.append(RANGE_ID_FIELD)

        if LOW_CHANNEL_FIELD in ao_dict:
            low_channel = ao_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self.ao_params.low_channel = int(low_channel)
        else:
            self._invalid_fields.append(LOW_CHANNEL_FIELD)

        if HIGH_CHANNEL_FIELD in ao_dict:
            high_channel = ao_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self.ao_params.high_channel = int(high_channel)
        else:
            self._invalid_fields.append(HIGH_CHANNEL_FIELD)

        if SCAN_FLAGS_FIELD in ao_dict:
            scan_flags = ao_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                self.ao_params.scan_flags = list_bitwise_or(scan_flags)
            elif is_int_or_raise(scan_flags):
                self.ao_params.scan_flags = int(scan_flags)
        else:
            self._invalid_fields.append(SCAN_FLAGS_FIELD)

    def check_invalid_fields(self):
        """Raises ValueError if at least one required field is missing in the settings."""
        if self._invalid_fields:
            invalid_fields_str = ", ".join(self._invalid_fields)
            raise ValueError("No fields found in the settings file: {}.".format(invalid_fields_str))

    def get_str(self):
        _daq_params = str(self.daq_params)
        _ai_params = str(self.ai_params)
        _ao_params = str(self.ao_params)
        settings_dict = str({"DAQ":_daq_params, "AI":_ai_params, "AO":_ao_params})
        settings_dict = settings_dict.replace("\'", "\"")               # need because json.loads does not recognie " ' "
        
        return settings_dict

class FrontSettings:
    """Parses configuration file with all necessary acquisition parameters."""

    def __init__(self, path: str):
        """Initializes dictionary and checks that all needed fields exist.

        After correct parsing it is possible to obtain ???? AM: add description.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if any field doesn't exist.
        """

        json_dict = JsonReader(path).json()

        if SERVER_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(SERVER_SETTINGS_FIELD))
        else:
            self._server_settings_dict = json_dict[SERVER_SETTINGS_FIELD]
            for field in [TANGO_FIELD, HTTP_FIELD]:
                if field not in self._server_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))
        
        if EXPERIMENT_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(EXPERIMENT_SETTINGS_FIELD))
        else:
            self._exp_settings_dict = json_dict[EXPERIMENT_SETTINGS_FIELD]
            for field in [PATHS_FIELD, SCAN_FIELD, MODULATION_FIELD]:
                if field not in self._exp_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))


        self._invalid_fields = []
        # only in that order
        self.parse_server_params()
        self.parse_experiment_params()
        self.check_invalid_fields()
        self.set_server_settings()
        self.set_exp_settings()

    def parse_server_params(self):
        for field in [TANGO_HOST_FIELD, DEVICE_PROXY_FIELD]:
            if field not in self._server_settings_dict[TANGO_FIELD] or \
                not isinstance(self._server_settings_dict[TANGO_FIELD][field], str):
                self._invalid_fields.append(field)

        for field in [HTTP_HOST]:
            if field not in self._server_settings_dict[HTTP_FIELD] or \
                not isinstance(self._server_settings_dict[HTTP_FIELD][field], str):
                self._invalid_fields.append(field)

    def parse_experiment_params(self):
        for field in [CALIB_PATH_FIELD, DATA_PATH_FIELD]:
            if field not in self._exp_settings_dict[PATHS_FIELD] or \
                not isinstance(self._exp_settings_dict[PATHS_FIELD][field], str):
                self._invalid_fields.append(field)

        # SampleRate is either a bare int (back-compat) or a per-mode map
        # (P1-31). ``resolve_sample_rate_map`` rejects bools and bad shapes.
        v = self._exp_settings_dict[SCAN_FIELD].get(SAMPLE_RATE_FIELD)
        try:
            resolve_sample_rate_map(v)
        except (ValueError, TypeError):
            self._invalid_fields.append(SAMPLE_RATE_FIELD)

        # JSON authors often write ``0`` instead of ``0.0``; accept both.
        for field in [FREQUENCY_FIELD, AMPLITUDE_FIELD, OFFSET_FIELD]:
            v = self._exp_settings_dict[MODULATION_FIELD].get(field)
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)):
                self._invalid_fields.append(field)

    def set_server_settings(self):
        if not self._invalid_fields:
            self.tango_host = self._server_settings_dict[TANGO_FIELD][TANGO_HOST_FIELD]
            self.device_proxy = self._server_settings_dict[TANGO_FIELD][DEVICE_PROXY_FIELD]
            self.http_host = self._server_settings_dict[HTTP_FIELD][HTTP_HOST]

    def get_server_settings(self):
        return {TANGO_FIELD: {
                    TANGO_HOST_FIELD: self.tango_host,
                    DEVICE_PROXY_FIELD: self.device_proxy
                    },
                HTTP_FIELD:{
                    HTTP_HOST: self.http_host
                    }
                }

    def set_exp_settings(self):
        if not self._invalid_fields:
            # Keep paths in their JSON form (relative paths stay relative to cwd).
            # Resolve to absolute only at the call site that actually needs an
            # absolute path; ``os.path.exists`` and ``open`` accept relative.
            self.calib_path = self._exp_settings_dict[PATHS_FIELD][CALIB_PATH_FIELD]
            self.data_path = self._exp_settings_dict[PATHS_FIELD][DATA_PATH_FIELD]
            # Keep the raw map for a faithful round-trip on save; expose the
            # per-mode map and the scalar ``default`` (used by the single UI
            # rate field) for callers (P1-31).
            self.sample_rate_raw = self._exp_settings_dict[SCAN_FIELD][SAMPLE_RATE_FIELD]
            self.sample_rate_by_mode = resolve_sample_rate_map(self.sample_rate_raw)
            self.sample_rate = self.sample_rate_by_mode["default"]
            self.modulation_frequency = self._exp_settings_dict[MODULATION_FIELD][FREQUENCY_FIELD]
            self.modulation_amplitude = self._exp_settings_dict[MODULATION_FIELD][AMPLITUDE_FIELD]
            self.modulation_offset = self._exp_settings_dict[MODULATION_FIELD][OFFSET_FIELD]
            # Carry the optional Limits / ChipPresence blocks verbatim so a GUI
            # save round-trips them (the front-end doesn't otherwise consume
            # them). None if absent.
            self.limits_raw = self._exp_settings_dict.get(LIMITS_FIELD)
            self.chip_presence_raw = self._exp_settings_dict.get(CHIP_PRESENCE_FIELD)

    def get_exp_settings(self):
        out = {PATHS_FIELD: {
                    CALIB_PATH_FIELD: self.calib_path,
                    DATA_PATH_FIELD: self.data_path
                    },
                SCAN_FIELD:{
                    SAMPLE_RATE_FIELD: self.sample_rate_raw
                    },
                MODULATION_FIELD: {
                    FREQUENCY_FIELD: self.modulation_frequency,
                    AMPLITUDE_FIELD: self.modulation_amplitude,
                    OFFSET_FIELD: self.modulation_offset
                    },
                }
        # Preserve the optional Limits / ChipPresence blocks on save (don't drop).
        limits_raw = getattr(self, "limits_raw", None)
        if limits_raw is not None:
            out[LIMITS_FIELD] = limits_raw
        chip_presence_raw = getattr(self, "chip_presence_raw", None)
        if chip_presence_raw is not None:
            out[CHIP_PRESENCE_FIELD] = chip_presence_raw
        return out

    def check_invalid_fields(self):
        """Raises ValueError if at least one required field is missing in the settings."""
        if self._invalid_fields:
            invalid_fields_str = ", ".join(self._invalid_fields)
            raise ValueError("Wrong or missing inputs in the settings file: {}.".format(invalid_fields_str))


class UISettings:
    """Front-end UI parameters loaded from ``ui_settings.json``.

    Independent of :class:`BackSettings` / :class:`FrontSettings` -- this
    file describes purely how the live-streaming UI is laid out and
    behaves: plot window seconds, fixed Y range, channel labels /
    colours / enabled-by-default, refresh cadence, slider bounds, demo
    AO defaults. No DAQ dependencies.

    Missing or absent fields fall back to baked-in defaults rather than
    raising -- the file is meant to be edited freely by the operator and
    we don't want a typo to crash the UI. Type coercion is permissive
    (str -> float etc.) for the same reason.
    """

    # Baked-in fallback defaults. Keep in sync with
    # ``src/pioner/settings/default_ui_settings.json`` -- the JSON file is what
    # an operator edits; this dict is just the safety net when the file is
    # missing or malformed.
    _DEFAULTS = {
        "window_seconds": 2.0,
        "y_min": -0.005,
        "y_max": 0.015,
        "max_plot_points": 2000,
        "refresh_interval_ms": 250,
        "channel_indices": (0, 1, 4, 5),
        "channel_labels": {0: "Uref", 1: "Umod", 2: "ch2", 3: "Uaux", 4: "Utpl", 5: "Uhtr"},
        "channel_colors": {
            0: "#D22525", 1: "#2544D2", 2: "#46D225",
            3: "#9F25D2", 4: "#D2B325", 5: "#5D5D5D",
        },
        "channel_enabled": {0: True, 1: True, 2: False, 3: False, 4: True, 5: True},
        "ring_max_seconds": 4.0,
        "demod_window_periods": 5,
        "demo_duration_seconds": 4.0,
        "demo_modulation_frequency": 37.5,
        "demo_modulation_amplitude": 2.0,
        "demo_ramp_peak": 2.0,
        "x_window_min": 0.1,
        "x_window_max": 10.0,
        "x_shift_max": 4.0,
        "y_span_min": 0.001,
        "y_span_max": 0.1,
    }

    def __init__(self, path: str = DEFAULT_UI_SETTINGS_FILE_REL_PATH):
        try:
            data = JsonReader(path).json()
        except (FileNotFoundError, ValueError) as exc:
            logging.getLogger(__name__).warning(
                "UISettings: failed to load %s (%s); using baked-in defaults", path, exc,
            )
            data = {}

        plot = data.get("Plot", {})
        ring = data.get("Ring", {})
        demod = data.get("Demod", {})
        demo = data.get("DemoAO", {})
        sliders = data.get("Sliders", {})

        self.window_seconds = float(plot.get("WindowSeconds", self._DEFAULTS["window_seconds"]))
        self.y_min = float(plot.get("YMin", self._DEFAULTS["y_min"]))
        self.y_max = float(plot.get("YMax", self._DEFAULTS["y_max"]))
        self.max_plot_points = int(plot.get("MaxPoints", self._DEFAULTS["max_plot_points"]))
        self.refresh_interval_ms = int(plot.get("RefreshIntervalMs", self._DEFAULTS["refresh_interval_ms"]))
        self.channel_indices = tuple(int(i) for i in plot.get("ChannelIndices", self._DEFAULTS["channel_indices"]))

        # JSON object keys are strings; coerce back to ints. Drop entries
        # whose key is not a valid int rather than crashing.
        self.channel_labels = self._coerce_int_dict(
            plot.get("ChannelLabels"), self._DEFAULTS["channel_labels"], str,
        )
        self.channel_colors = self._coerce_int_dict(
            plot.get("ChannelColors"), self._DEFAULTS["channel_colors"], str,
        )
        self.channel_enabled = self._coerce_int_dict(
            plot.get("ChannelEnabled"), self._DEFAULTS["channel_enabled"], bool,
        )

        self.ring_max_seconds = float(ring.get("MaxSeconds", self._DEFAULTS["ring_max_seconds"]))
        self.demod_window_periods = int(demod.get("WindowPeriods", self._DEFAULTS["demod_window_periods"]))

        self.demo_duration_seconds = float(demo.get("DurationSeconds", self._DEFAULTS["demo_duration_seconds"]))
        self.demo_modulation_frequency = float(demo.get("ModulationFrequency", self._DEFAULTS["demo_modulation_frequency"]))
        self.demo_modulation_amplitude = float(demo.get("ModulationAmplitudeV", self._DEFAULTS["demo_modulation_amplitude"]))
        self.demo_ramp_peak = float(demo.get("RampPeakV", self._DEFAULTS["demo_ramp_peak"]))

        self.x_window_min = float(sliders.get("XWindowMinSeconds", self._DEFAULTS["x_window_min"]))
        self.x_window_max = float(sliders.get("XWindowMaxSeconds", self._DEFAULTS["x_window_max"]))
        self.x_shift_max = float(sliders.get("XShiftMaxSeconds", self._DEFAULTS["x_shift_max"]))
        self.y_span_min = float(sliders.get("YSpanMinV", self._DEFAULTS["y_span_min"]))
        self.y_span_max = float(sliders.get("YSpanMaxV", self._DEFAULTS["y_span_max"]))

    @staticmethod
    def _coerce_int_dict(raw, default: dict, value_cast):
        """Convert a JSON-loaded ``{"0": "label", ...}`` dict to ``{0: "label", ...}``.

        Drops entries whose key cannot be parsed as int; falls back to
        ``default`` entirely if ``raw`` is missing.
        """
        if not isinstance(raw, dict):
            return dict(default)
        result = {}
        for key, value in raw.items():
            try:
                ik = int(key)
            except (TypeError, ValueError):
                continue
            result[ik] = value_cast(value)
        # Backfill any missing channel indices from defaults so the UI
        # always has a label/color/enabled flag for every channel.
        for ik, default_value in default.items():
            result.setdefault(ik, default_value)
        return result


if __name__ == '__main__':

    _path = SETTINGS_FILE_REL_PATH
    # settings = BackSettings(_path)
    settings = FrontSettings(_path)

    print(settings.get_exp_settings())

