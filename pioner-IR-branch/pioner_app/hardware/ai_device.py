import logging
import time
import numpy as np

try:
    from uldaq import (
        create_float_buffer,
        AiInputMode,
        Range,
        ScanOption,
        AInScanFlag,
        ScanStatus,
        AiQueueElement,
    )
    ULDAQ_IMPORT_ERROR = None
except Exception as exc:
    create_float_buffer = None
    AiInputMode = None
    Range = None
    ScanOption = None
    AInScanFlag = None
    ScanStatus = None
    AiQueueElement = None
    ULDAQ_IMPORT_ERROR = exc

from pioner_app.core.settings import settings

logger = logging.getLogger(__name__)


class AIDevice:
    CHANNEL_NAMES = ["Uref", "Umod", "Utpl", "Uhtr", "Uaux"]
    RANGE_LABELS = ["100 mV", "200 mV", "500 mV", "1 V", "2 V", "5 V", "10 V"]
    RANGE_FS = [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
    RANGE_ENUM_NAMES = [
        "BIPPT1VOLTS",
        "BIPPT2VOLTS",
        "BIPPT5VOLTS",
        "BIP1VOLTS",
        "BIP2VOLTS",
        "BIP5VOLTS",
        "BIP10VOLTS",
    ]
    RANGE_NAME_TO_FS = {
        "BIPPT1VOLTS": 0.1,
        "BIPPT2VOLTS": 0.2,
        "BIPPT5VOLTS": 0.5,
        "BIP1VOLTS": 1.0,
        "BIP2VOLTS": 2.0,
        "BIP5VOLTS": 5.0,
        "BIP10VOLTS": 10.0,
        "UNI1VOLTS": 1.0,
        "UNI2VOLTS": 2.0,
        "UNI5VOLTS": 5.0,
        "UNI10VOLTS": 10.0,
    }

    def __init__(self, ai_device):
        """Stub docstring."""
        if ULDAQ_IMPORT_ERROR is not None:
            raise RuntimeError(
                "ULDAQ AI support is unavailable in this Python environment."
            ) from ULDAQ_IMPORT_ERROR

        self.ai = ai_device
        self.low_channel = settings.ai_low
        self.high_channel = settings.ai_high
        self.channels = self.high_channel - self.low_channel + 1
        self.sample_rate = settings.sample_rate
        self.actual_sample_rate = settings.sample_rate
        self.buffer = None
        self.samples_per_channel = None
        self.channel_names = self._build_channel_names()
        self.range_positions = {
            name: int(getattr(settings, "input_gain_ranges", {}).get(name, 5))
            for name in self.channel_names
        }
        self.auto_gain_enabled = {
            name: bool(getattr(settings, "input_gain_auto", {}).get(name, True))
            for name in self.channel_names
        }
        self._range_enum_lookup = self._build_range_enum_lookup()
        self._active_ranges = {
            name: self._position_to_range_enum(pos)
            for name, pos in self.range_positions.items()
        }
        self._next_autogain_time = 0.0

    def _build_channel_names(self):
        """Stub for `build_channel_names`."""
        names = []
        configured = getattr(settings, "ai_names", {}) or {}
        for channel_index in range(self.channels):
            channel_number = self.low_channel + channel_index
            name = configured.get(str(channel_number)) or configured.get(channel_number)
            if not name and channel_index < len(self.CHANNEL_NAMES):
                name = self.CHANNEL_NAMES[channel_index]
            if not name:
                name = f"AI{channel_number}"
            names.append(str(name))
        return names

    def _supported_ranges(self):
        """Stub for `supported_ranges`."""
        try:
            info = self.ai.get_info()
            return list(info.get_ranges(AiInputMode(settings.ai_input_mode)) or [])
        except Exception:
            logger.exception("Failed to query supported AI ranges")
            return []

    def _enum_full_scale(self, enum_value):
        """Stub for `enum_full_scale`."""
        name = getattr(enum_value, "name", "")
        return float(self.RANGE_NAME_TO_FS.get(name, self.RANGE_FS[-1]))

    def _build_range_enum_lookup(self):
        """Stub for `build_range_enum_lookup`."""
        lookup = {}
        if Range is None:
            return lookup
        for idx, enum_name in enumerate(self.RANGE_ENUM_NAMES):
            enum_value = getattr(Range, enum_name, None)
            if enum_value is not None:
                lookup[idx] = enum_value
        return lookup

    def _clamp_position(self, position):
        """Stub for `clamp_position`."""
        return max(0, min(int(position), len(self.RANGE_LABELS) - 1))

    def _position_to_range_enum(self, position):
        """Stub for `position_to_range_enum`."""
        position = self._clamp_position(position)
        requested_fs = self.RANGE_FS[position]
        supported = self._supported_ranges()
        if supported:
            supported_sorted = sorted(supported, key=self._enum_full_scale)
            for enum_value in supported_sorted:
                if self._enum_full_scale(enum_value) >= requested_fs:
                    return enum_value
            return supported_sorted[-1]
        enum_value = self._range_enum_lookup.get(position)
        if enum_value is not None:
            return enum_value
        fallback = getattr(Range, "BIP10VOLTS", None)
        return fallback if fallback is not None else Range(settings.ai_range)

    def _position_full_scale(self, position):
        """Stub for `position_full_scale`."""
        return float(self.RANGE_FS[self._clamp_position(position)])

    def _queue_range_for_channel(self, channel_index):
        """Stub for `queue_range_for_channel`."""
        name = self.channel_names[channel_index]
        position = self.range_positions.get(name, 5)
        return self._position_to_range_enum(position)

    def _configure_queue(self):
        """Stub for `configure_queue`."""
        if AiQueueElement is None or not hasattr(self.ai, 'a_in_load_queue'):
            return
        try:
            info = self.ai.get_info()
            max_queue_length = int(info.get_max_queue_length(AiInputMode(settings.ai_input_mode)))
            if max_queue_length < self.channels:
                logger.warning("AI queue length %s is smaller than active channels %s; skipping per-channel gains", max_queue_length, self.channels)
                return
        except Exception:
            logger.exception("Failed to query AI queue capabilities")
            return
        try:
            queue = []
            input_mode = AiInputMode(settings.ai_input_mode)
            for channel_index in range(self.channels):
                element = AiQueueElement()
                element.channel = self.low_channel + channel_index
                element.input_mode = input_mode
                element.range = self._queue_range_for_channel(channel_index)
                queue.append(element)
            self.ai.a_in_load_queue(queue)
            self._active_ranges = {
                name: self._position_to_range_enum(self.range_positions[name])
                for name in self.channel_names
            }
        except Exception:
            logger.exception("Failed to load AI gain queue; falling back to global range")

    def get_gain_state(self):
        """Stub for `get_gain_state`."""
        return {
            "ranges": dict(self.range_positions),
            "auto_gain": dict(self.auto_gain_enabled),
        }

    def set_channel_gains(self, ranges=None, auto_gain=None):
        """Stub for `set_channel_gains`."""
        ranges = ranges or {}
        auto_gain = auto_gain or {}
        for name in self.channel_names:
            if name in ranges:
                self.range_positions[name] = self._clamp_position(ranges[name])
            if name in auto_gain:
                self.auto_gain_enabled[name] = bool(auto_gain[name])
        self._active_ranges = {
            name: self._position_to_range_enum(self.range_positions[name])
            for name in self.channel_names
        }

    def allocate_buffer(self, samples):
        """Stub for `allocate_buffer`."""
        logger.info(f"Allocating AI buffer: {samples} samples")
        self.samples_per_channel = samples
        self.buffer = create_float_buffer(self.channels, samples)
        return self.buffer

    def _start_scan(self, scan_option):
        """Stub for `start_scan`."""
        logger.info("Starting AI scan")
        self._configure_queue()
        actual_rate = self.ai.a_in_scan(
            self.low_channel,
            self.high_channel,
            AiInputMode(settings.ai_input_mode),
            self._queue_range_for_channel(0),
            self.samples_per_channel,
            self.sample_rate,
            scan_option,
            AInScanFlag.DEFAULT,
            self.buffer,
        )
        self._update_actual_sample_rate(actual_rate)

    def _update_actual_sample_rate(self, actual_rate):
        """Stores the actual scan rate reported by the hardware."""
        if actual_rate is None:
            self.actual_sample_rate = self.sample_rate
            return
        try:
            actual_rate = float(actual_rate)
        except (TypeError, ValueError):
            self.actual_sample_rate = self.sample_rate
            return

        self.actual_sample_rate = actual_rate
        if abs(actual_rate - float(self.sample_rate)) > 1e-6:
            logger.warning("AI actual sample rate differs from requested: requested=%s actual=%s", self.sample_rate, actual_rate)

    def start_scan(self):
        """Stub for `start_scan`."""
        self._start_scan(ScanOption.DEFAULTIO)

    def start_scan_continious(self):
        """Stub for `start_scan_continious`."""
        self._start_scan(ScanOption.CONTINUOUS)

    def get_progress(self):
        """Stub for `get_progress`."""
        status, transfer = self.ai.get_scan_status()
        return status, transfer.current_scan_count

    def read_available_data(self, samples):
        """Stub for `read_available_data`."""
        data = np.array(self.buffer[:samples * self.channels])
        data = data.reshape(-1, self.channels)
        return data

    def autogain_update_from_data(self, data):
        """Stub for `autogain_update_from_data`."""
        if data is None or len(data) == 0:
            return None
        now = time.monotonic()
        if now < self._next_autogain_time:
            return None

        changed = False
        for channel_index, name in enumerate(self.channel_names):
            if not self.auto_gain_enabled.get(name, False):
                continue
            position = self.range_positions.get(name, 5)
            full_scale = self._position_full_scale(position)
            values = np.asarray(data[:, channel_index], dtype=float)
            peak = float(np.max(np.abs(values))) if values.size else 0.0

            new_position = position
            if peak >= full_scale * 0.92 and position < len(self.RANGE_LABELS) - 1:
                new_position = position + 1
            elif 1e-4 < peak <= full_scale * 0.12 and position > 0:
                new_position = position - 1

            if new_position != position:
                self.range_positions[name] = new_position
                changed = True

        if not changed:
            return None

        self._next_autogain_time = now + 0.5
        self._active_ranges = {
            name: self._position_to_range_enum(self.range_positions[name])
            for name in self.channel_names
        }
        logger.info("AI autogain updated ranges: %s", self.range_positions)
        return self.get_gain_state()

    def stop(self):
        """Stub for `stop`."""
        logger.info("Stopping AI scan")
        try:
            self.ai.scan_stop()
        except Exception:
            logger.exception("Error stopping AI scan")


