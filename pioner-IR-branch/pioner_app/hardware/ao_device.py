import logging
import numpy as np

try:
    from uldaq import (
        create_float_buffer,
        Range,
        ScanOption,
        AOutFlag,
        AOutScanFlag,
    )
    ULDAQ_IMPORT_ERROR = None
except Exception as exc:
    create_float_buffer = None
    Range = None
    ScanOption = None
    AOutFlag = None
    AOutScanFlag = None
    ULDAQ_IMPORT_ERROR = exc

from pioner_app.core.settings import settings


logger = logging.getLogger(__name__)


class AODevice:

    def __init__(self, ao_device):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        if ULDAQ_IMPORT_ERROR is not None:
            raise RuntimeError(
                "ULDAQ AO support is unavailable in this Python environment."
            ) from ULDAQ_IMPORT_ERROR

        self.ao = ao_device

        self.low_channel = settings.ao_low
        self.high_channel = settings.ao_high

        self.channels = self.high_channel - self.low_channel + 1

        self.samples_per_channel = None
        self.buffer = None
        self.sample_rate = settings.sample_rate
        self.actual_sample_rate = settings.sample_rate

    def allocate_buffer(self, samples):

        """???????? ?????? `allocate_buffer`."""
        logger.info(f"Allocating AO buffer: {samples} samples")

        self.samples_per_channel = samples

        self.buffer = create_float_buffer(self.channels, samples)

        return self.buffer

    def fill_buffer(self, *signals):

        """???????? ?????? `fill_buffer`."""
        logger.info("Filling AO buffer")

        lengths = [len(s) for s in signals]

        if len(set(lengths)) != 1:
            raise ValueError(f"Signal lengths mismatch: {lengths}")

        samples = lengths[0]

        if samples != self.samples_per_channel:
            raise ValueError(
                f"Signal length {samples} != allocated samples {self.samples_per_channel}"
            )

        interleaved = np.column_stack(signals).astype(np.float64).ravel()
        self.buffer[:] = interleaved

    def start_scan(self):

        """????????? ?????? `start_scan`."""
        logger.info("Starting AO scan")

        actual_rate = self.ao.a_out_scan(
            self.low_channel,
            self.high_channel,
            Range(settings.ao_range),
            self.samples_per_channel,
            self.sample_rate,
            ScanOption.DEFAULTIO,
            AOutScanFlag.DEFAULT,
            self.buffer
        )
        self._update_actual_sample_rate(actual_rate, "AO")

    def start_scan_continious(self):

        """????????? ?????? `start_scan_continious`."""
        logger.info("Starting AO scan continious")

        actual_rate = self.ao.a_out_scan(
            self.low_channel,
            self.high_channel,
            Range(settings.ao_range),
            self.samples_per_channel,
            self.sample_rate,
            ScanOption.CONTINUOUS,
            AOutScanFlag.DEFAULT,
            self.buffer
        )
        self._update_actual_sample_rate(actual_rate, "AO")


    def start_single_channel_wave(self, channel, signal, sample_rate=None, continuous=True):

        """Запускает wave scan на одном AO-канале."""
        signal = np.asarray(signal, dtype=np.float64)
        samples = int(len(signal))
        if samples <= 0:
            raise ValueError("Single-channel AO signal is empty")

        self.samples_per_channel = samples
        self.sample_rate = int(sample_rate or self.sample_rate)
        self.actual_sample_rate = self.sample_rate
        self.buffer = create_float_buffer(1, samples)
        self.buffer[:] = signal

        option = ScanOption.CONTINUOUS if continuous else ScanOption.DEFAULTIO
        logger.info("Starting single-channel AO wave: ch=%s samples=%s continuous=%s", channel, samples, continuous)
        actual_rate = self.ao.a_out_scan(
            int(channel),
            int(channel),
            Range(settings.ao_range),
            samples,
            self.sample_rate,
            option,
            AOutScanFlag.DEFAULT,
            self.buffer,
        )
        self._update_actual_sample_rate(actual_rate, "AO")

    def _update_actual_sample_rate(self, actual_rate, prefix):

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
            logger.warning("%s actual sample rate differs from requested: requested=%s actual=%s", prefix, self.sample_rate, actual_rate)

    def write_static(self, values_by_channel, stop_scan=True):

        """?????????? ?????? `write_static`."""
        logger.info("Writing static AO values: %s", values_by_channel)

        if stop_scan:
            try:
                self.stop()
            except Exception:
                logger.exception("Failed to stop AO before static write")

        ao_range = Range(settings.ao_range)
        for channel, value in values_by_channel.items():
            if channel < self.low_channel or channel > self.high_channel:
                continue
            self.ao.a_out(channel, ao_range, AOutFlag.DEFAULT, float(value))

    def stop(self):

        """????????????? ?????? `stop`."""
        logger.info("Stopping AO scan")

        try:
            self.ao.scan_stop()
        except Exception:
            logger.exception("Error stopping AO scan")


class AOGenerator:

    def __init__(self, channels):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.channels = channels
        self.channel_buffers = {ch: [] for ch in range(channels)}

    def _samples(self, duration):
        """???????? ?????? `samples`."""
        return int(duration * (settings.sample_rate / 1000))

    def ramp(self, channel, duration, start, stop):
        """???????? ?????? `ramp`."""
        samples = self._samples(duration)
        logger.info(f"Ramp ch{channel} {start}->{stop} duration={duration} ms")
        signal = np.linspace(start, stop, samples)
        self.channel_buffers[channel].append(signal)

    def ramp_down(self, channel, duration, start, stop):
        """???????? ?????? `ramp_down`."""
        samples = self._samples(duration)
        logger.info(f"RampDown ch{channel} {start}->{stop} duration={duration} ms")
        signal = np.linspace(start, stop, samples)
        self.channel_buffers[channel].append(signal)

    def isotherm(self, channel, duration, value):
        """???????? ?????? `isotherm`."""
        samples = self._samples(duration)
        logger.info(f"Isotherm ch{channel} value={value} duration={duration} ms")
        signal = np.ones(samples) * value
        self.channel_buffers[channel].append(signal)

    def sine(self, channel, duration, frequency, amplitude, offset=0):
        """???????? ?????? `sine`."""
        samples = self._samples(duration)
        logger.info(
            f"Sine ch{channel} f={frequency}Hz amp={amplitude} duration={duration} ms"
        )
        t = np.arange(samples) / settings.sample_rate
        signal = offset + amplitude * np.sin(2 * np.pi * frequency * t)
        self.channel_buffers[channel].append(signal)

    def build(self):
        """???????? ?????? `build`."""
        logger.info("Building AO signals")
        signals = []

        for ch in range(self.channels):
            if not self.channel_buffers[ch]:
                signals.append(np.zeros(1))
                continue

            signal = np.concatenate(self.channel_buffers[ch])
            signals.append(signal)

        lengths = [len(s) for s in signals]
        max_len = max(lengths)

        for i, s in enumerate(signals):
            if len(s) < max_len:
                padding = np.ones(max_len - len(s)) * s[-1]
                signals[i] = np.concatenate((s, padding))

        logger.info(f"AO signal length {max_len} samples")
        return signals, max_len


class AOGeneratorProfile:
    def __init__(self, profile, sample_rate):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.profile = profile
        self.sample_rate = sample_rate


class AOStreamSHGenerator:
    def __init__(self, sample_rate):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.sample_rate = sample_rate
        self.freq = 0.0
        self.amp = 0.0
        self.offset = 0.0
        self.mode = "voltage"
        self.start_value = 0.0
        self.end_value = 0.0
        self.rate_per_min = 0.0
        self.converter = None
        self.sample_index = 0
        self.chunk_index = 0
        self.completed = False
        self.hold_final_value = False
        self.chunk_size = 0
        self.total_chunks = 1
        self._carrier_phase = 0.0
        self.mod_final_freq = 0.0
        self.mod_final_amp = 0.0
        self.mod_start_phase_deg = 0.0
        self.mod_final_phase_deg = 0.0
        self.mod_freq_ramp = False
        self.mod_amp_ramp = False
        self.mod_phase_ramp = False
        self.mod_ramp_steps = 1
        self.x2_mode = False

    def set_modulation(self, freq, amp, offset):
        """????????????? ?????? `set_modulation`."""
        self.freq = float(freq)
        self.amp = float(amp)
        self.offset = float(offset)
        self.mod_final_freq = float(freq)
        self.mod_final_amp = float(amp)

    def set_chunk_geometry(self, chunk_size, duration_sec):
        """????????????? ?????? `set_chunk_geometry`."""
        self.chunk_size = max(1, int(chunk_size))
        total_samples = max(1, int(np.ceil(max(float(duration_sec), 0.0) * self.sample_rate)))
        self.total_chunks = max(1, int(np.ceil(total_samples / self.chunk_size)))

    def set_modulation_ramps(
        self,
        final_freq=None,
        final_amp=None,
        final_phase_deg=None,
        ramp_steps=1,
        enable_freq_ramp=False,
        enable_amp_ramp=False,
        enable_phase_ramp=False,
        x2_mode=False,
    ):
        """????????????? ?????? `set_modulation_ramps`."""
        self.mod_final_freq = float(self.freq if final_freq is None else final_freq)
        self.mod_final_amp = float(self.amp if final_amp is None else final_amp)
        self.mod_start_phase_deg = 0.0
        self.mod_final_phase_deg = float(0.0 if final_phase_deg is None else final_phase_deg)
        self.mod_freq_ramp = bool(enable_freq_ramp)
        self.mod_amp_ramp = bool(enable_amp_ramp)
        self.mod_phase_ramp = bool(enable_phase_ramp)
        self.mod_ramp_steps = max(1, int(ramp_steps))
        self.x2_mode = bool(x2_mode)

    def set_heating(self, mode, start_value, end_value, rate_per_min, converter=None, hold_final_value=False):
        """????????????? ?????? `set_heating`."""
        self.mode = mode
        self.start_value = float(start_value)
        self.end_value = float(end_value)
        self.rate_per_min = float(rate_per_min)
        self.converter = converter
        self.sample_index = 0
        self.chunk_index = 0
        self.completed = False
        self.hold_final_value = bool(hold_final_value)
        self._carrier_phase = 0.0

    def _convert_output(self, values):
        """??????????? ?????? `convert_output`."""
        values = np.asarray(values, dtype=float)
        if self.mode == "temperature":
            if self.converter is None:
                raise ValueError("Temperature streaming requires converter")
            return np.asarray(self.converter(values), dtype=float)
        return values

    def _modulation_step_fraction(self):
        """???????? ?????? `modulation_step_fraction`."""
        active = self.mod_freq_ramp or self.mod_amp_ramp or self.mod_phase_ramp
        if not active:
            return 0.0
        steps = max(self.mod_ramp_steps, 2)
        if self.total_chunks <= 1:
            return 1.0
        progress = min(max(self.chunk_index / max(self.total_chunks - 1, 1), 0.0), 1.0)
        step_index = min(int(np.floor(progress * steps)), steps - 1)
        return step_index / float(steps - 1)

    def current_modulation_values(self):
        """???????? ?????? `current_modulation_values`."""
        frac = self._modulation_step_fraction()
        freq = self.freq + (self.mod_final_freq - self.freq) * frac if self.mod_freq_ramp else self.freq
        amp = self.amp + (self.mod_final_amp - self.amp) * frac if self.mod_amp_ramp else self.amp
        phase_deg = self.mod_start_phase_deg + (self.mod_final_phase_deg - self.mod_start_phase_deg) * frac if self.mod_phase_ramp else self.mod_start_phase_deg
        demod_freq = freq * (2.0 if self.x2_mode else 1.0)
        return {
            "carrier_freq": float(freq),
            "demod_freq": float(demod_freq),
            "amp": float(amp),
            "phase_deg": float(phase_deg),
            "offset": float(self.offset),
            "step_fraction": float(frac),
        }

    def _target_values(self, chunk_size):
        """???????? ?????? `target_values`."""
        t = (np.arange(chunk_size, dtype=float) + self.sample_index) / self.sample_rate
        if self.rate_per_min == 0:
            values = np.full(chunk_size, self.start_value, dtype=float)
        else:
            direction = 1.0 if self.end_value >= self.start_value else -1.0
            rate_per_sec = abs(self.rate_per_min) / 60.0
            values = self.start_value + direction * rate_per_sec * t
            if direction > 0:
                values = np.minimum(values, self.end_value)
            else:
                values = np.maximum(values, self.end_value)
        return self._convert_output(values)

    def _final_output(self, chunk_size):
        """???????? ?????? `final_output`."""
        final_values = np.full(chunk_size, self.end_value, dtype=float)
        return self._convert_output(final_values)

    def generate_chunk(self, chunk_size):
        """???????? ?????? `generate_chunk`."""
        if self.completed and not self.hold_final_value:
            return None, None

        mod_state = self.current_modulation_values()
        carrier_freq = mod_state["carrier_freq"]
        amp = mod_state["amp"]
        phase_offset = np.deg2rad(mod_state["phase_deg"])

        t = np.arange(chunk_size, dtype=float) / self.sample_rate
        if carrier_freq > 0:
            mod = self.offset + amp * np.sin(self._carrier_phase + phase_offset + 2 * np.pi * carrier_freq * t)
            self._carrier_phase = (self._carrier_phase + 2 * np.pi * carrier_freq * (chunk_size / self.sample_rate)) % (2 * np.pi)
        else:
            mod = np.full(chunk_size, self.offset + amp * np.sin(self._carrier_phase + phase_offset), dtype=float)

        if self.completed and self.hold_final_value:
            heat = self._final_output(chunk_size)
        else:
            heat = self._target_values(chunk_size)

        self.sample_index += chunk_size
        self.chunk_index += 1

        if not self.completed and chunk_size > 0:
            elapsed = (self.sample_index - 1) / self.sample_rate
            if self.start_value <= self.end_value:
                done_value = self.start_value + abs(self.rate_per_min) / 60.0 * elapsed
                self.completed = done_value >= self.end_value
            else:
                done_value = self.start_value - abs(self.rate_per_min) / 60.0 * elapsed
                self.completed = done_value <= self.end_value

        return mod, heat




