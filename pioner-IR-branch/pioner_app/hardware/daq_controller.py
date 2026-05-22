import logging
import time
import numpy as np
from pathlib import Path
from threading import Thread

from PyQt5.QtCore import QObject, pyqtSignal

from pioner_app.core.experiment_manager import ExperimentManager
from pioner_app.core.calibration import Calibration
from pioner_app.core.settings import settings
from pioner_app.backends import create_hardware_backend
from pioner_app.hardware.ao_device import AOStreamSHGenerator
from pioner_app.core.basemath import temperature_to_voltage


logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parents[2]


class DAQController(QObject):
    progress_changed = pyqtSignal(int)
    input_gains_changed = pyqtSignal(dict, dict)

    _instance = None

    def __new__(cls):
        """??????? ????????? ??????."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super().__init__()

        if hasattr(self, "_initialized"):
            return

        self.generator = None
        self._ao_timer = None
        self._ao_thread = None
        self._modulation_thread = None
        self._running = False
        self._modulation_running = False
        self._acquisition_running = False
        self._acquisition_owner = None
        self._initialized = True
        self.device = None
        self.em = None
        self.calibration = None
        self.device_name = None
        self.connection_mode = getattr(settings, "connection_mode", "direct")
        self._acquisition_points_per_channel = None
        self._fast_heat_running = False

    def set_connection_mode(self, mode):
        """????????????? ?????? `set_connection_mode`."""
        if mode:
            self.connection_mode = mode.strip().lower()

    def connect(self):
        """?????????? ?????? `connect`."""
        if self.device:
            return

        self.device = create_hardware_backend(self.connection_mode)
        self.device.connect()

        try:
            descriptor = getattr(self.device, "descriptor", None)
            name = getattr(self.device, "device_name", None)
            if not name and descriptor is not None:
                name = getattr(descriptor, "product_name", None)
            if not name and descriptor is not None:
                name = getattr(descriptor, "productName", None)
        except Exception:
            name = None

        self.device_name = name or "DAQ"

        self.calibration = Calibration()
        self.calibration.read(str(BASE_DIR / "default_calibration.json"))
        self.em = ExperimentManager(self.device, calibration=self.calibration)
        self.apply_input_gains(
            getattr(settings, "input_gain_ranges", {}),
            getattr(settings, "input_gain_auto", {}),
            restart=False,
            emit_signal=False,
        )

        logger.info("DAQController connected via %s", self.connection_mode)

    def disconnect(self):
        """????????? ?????? `disconnect`."""
        if self.device:
            self.device.disconnect()

        self.device = None
        self.em = None
        self._acquisition_points_per_channel = None
        logger.info("DAQController disconnected")

    def set_sample_rate(self, rate):
        """????????? sample rate ? ????????????? ???????? continuous scan."""
        settings.sample_rate = rate
        if not self.em:
            return

        was_running = bool(self._acquisition_running)
        owner = self._acquisition_owner
        points = self._acquisition_points_per_channel or getattr(self.em, "points_per_channel", None) or 2000

        if was_running:
            self.stop_acquisition(force=True)

        self.em.ai.sample_rate = rate
        self.em.ao.sample_rate = rate

        if was_running:
            self.start_acquisition(owner=owner or "signals", points_per_channel=points)

    def get_input_gains_state(self):
        """?????????? ?????? `get_input_gains_state`."""
        if self.em:
            return self.em.ai.get_gain_state()
        return {
            "ranges": dict(getattr(settings, "input_gain_ranges", {})),
            "auto_gain": dict(getattr(settings, "input_gain_auto", {})),
        }

    def apply_input_gains(self, ranges=None, auto_gain=None, restart=True, emit_signal=True):
        """????????? ?????? `apply_input_gains`."""
        ranges = dict(ranges or {})
        auto_gain = dict(auto_gain or {})

        merged_ranges = dict(getattr(settings, "input_gain_ranges", {}))
        merged_ranges.update(ranges)
        merged_auto = dict(getattr(settings, "input_gain_auto", {}))
        merged_auto.update(auto_gain)

        settings.input_gain_ranges = merged_ranges
        settings.input_gain_auto = merged_auto

        if not self.em:
            if emit_signal:
                self.input_gains_changed.emit(dict(merged_ranges), dict(merged_auto))
            return {"ranges": merged_ranges, "auto_gain": merged_auto}

        was_running = bool(restart and self._acquisition_running)
        owner = self._acquisition_owner
        points = self._acquisition_points_per_channel or getattr(self.em, "points_per_channel", None) or 2000

        if was_running:
            self.stop_acquisition(force=True)

        self.em.ai.set_channel_gains(merged_ranges, merged_auto)
        state = self.em.ai.get_gain_state()
        settings.input_gain_ranges = dict(state["ranges"])
        settings.input_gain_auto = dict(state["auto_gain"])

        if was_running:
            self.start_acquisition(owner=owner or "signals", points_per_channel=points)

        if emit_signal:
            self.input_gains_changed.emit(dict(state["ranges"]), dict(state["auto_gain"]))
        return state

    def _maybe_apply_autogain(self, data):
        """???????? ?????? `maybe_apply_autogain`."""
        if not self.em or not self._acquisition_running or data is None:
            return
        if self._acquisition_owner != "signals":
            return

        state = self.em.ai.autogain_update_from_data(data)
        if not state:
            return

        owner = self._acquisition_owner or "signals"
        points = self._acquisition_points_per_channel or getattr(self.em, "points_per_channel", None) or 2000
        self.stop_acquisition(force=True)
        self.em.ai.set_channel_gains(state.get("ranges", {}), state.get("auto_gain", {}))
        self.start_acquisition(owner=owner, points_per_channel=points)
        settings.input_gain_ranges = dict(state["ranges"])
        settings.input_gain_auto = dict(state["auto_gain"])
        self.input_gains_changed.emit(dict(state["ranges"]), dict(state["auto_gain"]))

    def start_modulation(self, freq, amp, offset, phase_deg=0.0):
        """????????? ?????? `start_modulation`."""
        if hasattr(self.device, "set_modulation"):
            self.device.set_modulation(freq, amp, offset)
            return
        if not self.em:
            raise RuntimeError("DAQ not connected")

        try:
            self.em.stop_ao_continuous()
        except Exception:
            pass

        try:
            self.em.ao.stop()
        except Exception:
            pass

        freq = float(freq)
        amp = float(amp)
        offset = float(offset)
        phase_rad = np.deg2rad(float(phase_deg))

        if freq > 0:
            samples_per_period = int(max(256, min(2048, round(400000.0 / max(freq, 0.1)))))
            ao_sample_rate = int(round(freq * samples_per_period))
            n = np.arange(samples_per_period, dtype=float)
            current_ma = offset + amp * np.sin(phase_rad + 2.0 * np.pi * (n / float(samples_per_period)))
        else:
            ao_sample_rate = max(int(getattr(settings, "sample_rate", 10000)), 1000)
            current_ma = np.full(ao_sample_rate, offset, dtype=float)

        ch0 = self._heater_current_to_voltage(current_ma)
        self.em.ao.start_single_channel_wave(self.em.ao.low_channel, ch0, sample_rate=ao_sample_rate, continuous=True)

    def stop_modulation(self):
        """????????????? ?????? `stop_modulation`."""
        self._modulation_running = False
        self._join_modulation_thread()
        if self.em:
            try:
                self.em.stop_ao_continuous()
            except Exception:
                pass
            try:
                self.em.ao.stop()
            except Exception:
                pass
            self.reset_ao_outputs()

    def reset_ao_outputs(self, ao0=0.1, ao1=0.0):
        """?????????? ?????? `reset_ao_outputs`."""
        if not getattr(self, "em", None):
            return
        try:
            values = {self.em.ao.low_channel: float(ao0)}
            if self.em.ao.low_channel + 1 <= self.em.ao.high_channel:
                values[self.em.ao.low_channel + 1] = float(ao1)
            self.em.ao.write_static(values)
        except Exception:
            logger.exception("Failed to reset AO outputs to baseline")

    def _heater_current_to_voltage(self, current_mA):
        """???????? ?????? `heater_current_to_voltage`."""
        current_mA = np.asarray(current_mA, dtype=float)
        return (current_mA - self.calibration.ihtr0) / self.calibration.ihtr1

    def _temperature_to_voltage_array(self, values):
        """???????? ?????? `temperature_to_voltage_array`."""
        return np.asarray(temperature_to_voltage(values, calibration=self.calibration), dtype=float)

    def _reset_all_scans(self):
        """?????????? ?????? `reset_all_scans`."""
        if not self.em:
            return

        try:
            self.em.ao.stop()
        except Exception:
            pass

        try:
            self.em.ai.stop()
        except Exception:
            pass

        try:
            self.em.stop_continuous()
        except Exception:
            pass

        self._acquisition_running = False
        self._acquisition_owner = None

        time.sleep(0.1)

    def _join_ao_thread(self, timeout=2.0):
        """???????? ?????? `join_ao_thread`."""
        thread = self._ao_thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._ao_thread = None

    def _join_modulation_thread(self, timeout=2.0):
        """???????? ?????? `join_modulation_thread`."""
        thread = self._modulation_thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._modulation_thread = None

    def stop_all_hardware_processes(self):
        """????????????? ?????? `stop_all_hardware_processes`."""
        self._running = False
        self._modulation_running = False

        try:
            if self.em:
                self.em.ao.stop()
        except Exception:
            pass

        try:
            if self.em:
                self.em.ai.stop()
        except Exception:
            pass

        try:
            if self.em:
                self.em.stop_continuous()
        except Exception:
            pass

        try:
            if self.em:
                self.em.stop_ao_continuous()
        except Exception:
            pass

        self._join_modulation_thread()
        self._join_ao_thread()
        self._acquisition_running = False
        self._acquisition_owner = None
        time.sleep(0.1)

    def prepare_for_experiment(self):
        """?????????????? ?????? `prepare_for_experiment`."""
        self.generator = None
        self.stop_all_hardware_processes()
        self.reset_ao_outputs()

    def start_acquisition(self, owner="signals", points_per_channel=2000):
        """????????? ?????? `start_acquisition`."""
        if not self.em:
            raise RuntimeError("DAQ not connected")
        if self._acquisition_running:
            return self._acquisition_owner == owner

        self.em.start_continuous(points_per_channel=points_per_channel)
        self._acquisition_running = True
        self._acquisition_owner = owner
        self._acquisition_points_per_channel = points_per_channel
        return True

    def read_data(self, apply_autogain=True):
        """?????? ?????? `read_data`."""
        if self.device is None:
            return None

        if hasattr(self.device, "read"):
            data = self.device.read(2000)
            self._last_data = data
            return data

        if not self.em:
            return None

        data = self.em.read_continuous()
        if data is not None:
            self._last_data = data
            if apply_autogain:
                self._maybe_apply_autogain(data)
        return data

    def peek_data(self, points=None, apply_autogain=False):
        """???????? ?????? `peek_data`."""
        if self.device is None or not self.em:
            return None
        data = self.em.peek_continuous(count=points)
        if data is not None:
            self._last_data = data
            if apply_autogain:
                self._maybe_apply_autogain(data)
        return data

    def get_last_data(self):
        """?????????? ?????? `get_last_data`."""
        return getattr(self, "_last_data", None)

    def stop_acquisition(self, owner=None, force=False):
        """????????????? ?????? `stop_acquisition`."""
        if not self.em or not self._acquisition_running:
            return False
        if not force and owner is not None and self._acquisition_owner not in (None, owner):
            return False

        self.em.stop_continuous()
        self._acquisition_running = False
        self._acquisition_owner = None
        return True

    def is_acquisition_running(self):
        """????????? ?????? `is_acquisition_running`."""
        return self._acquisition_running

    def acquisition_owner(self):
        """???????? ?????? `acquisition_owner`."""
        return self._acquisition_owner

    def run_fast_heat_profile(self, profile_dict):
        """Runs fast heating through the dedicated finite profile path."""
        if not self.em:
            raise RuntimeError("DAQ not connected")

        self._fast_heat_running = True
        self.prepare_for_experiment()

        try:
            return self.em.run_fast_heat_profile(
                profile_dict,
                progress_cb=self.progress_changed.emit,
            )
        finally:
            self._fast_heat_running = False
            self.reset_ao_outputs()

    def run_fast_heat_async(self, profile_dict):
        """????????? ?????? `run_fast_heat_async`."""
        from threading import Thread

        def worker():
            """???????? ?????? `worker`."""
            try:
                self.run_fast_heat_profile(profile_dict)
            except Exception as exc:
                logger.exception("Fast heat error: %s", exc)

        Thread(target=worker, daemon=True).start()

    def start_temp_ramp(self, start_val, end_val, rate, freq, amp, offset):
        """????????? ?????? `start_temp_ramp`."""
        return

    def start_slow_heating(
        self,
        freq,
        amp,
        offset,
        mode,
        start_value,
        end_value,
        rate_per_min,
        hold_final_value=False,
        demod_periods=5,
        modulation_ramps=None,
        point_interval_sec=1.0,
    ):
        """Запускает медленный нагрев через единый AO-прогон без блокировки UI."""
        if not self.em:
            raise RuntimeError("DAQ not connected")
        if rate_per_min == 0:
            raise ValueError("Slow heating rate cannot be zero")

        self.prepare_for_experiment()

        duration_sec = abs(end_value - start_value) / abs(rate_per_min) * 60.0 if end_value != start_value else max(10.0, 5.0 / max(freq, 0.1))
        duration_sec = max(duration_sec, max(5.0, 5.0 / max(freq, 0.1)))
        ramps = dict(modulation_ramps or {})

        fs_ai = settings.sample_rate
        demod_frequency = float(freq) * (2.0 if ramps.get("x2_mode") else 1.0)
        periods_for_buffer = max(int(demod_periods), 3)
        min_point_interval_sec = max(float(point_interval_sec), 0.25)
        samples_per_period_ai = max(1, int(round(fs_ai / max(demod_frequency, 0.1)))) if demod_frequency > 0 else max(1, int(fs_ai * 0.2))
        analysis_chunk_size = max(
            samples_per_period_ai * (periods_for_buffer + 1),
            samples_per_period_ai * 3,
            int(fs_ai * min_point_interval_sec),
        )
        ai_buffer = max(analysis_chunk_size * 4, 2000)
        self.start_acquisition(owner="slow_heating", points_per_channel=ai_buffer)

        self._running = True
        self._slow_heating_meta = {
            "mode": mode,
            "freq": float(freq),
            "amp": float(amp),
            "offset": float(offset),
            "demod_frequency": float(demod_frequency),
            "carrier_frequency": float(freq),
            "current_amp": float(amp),
            "current_phase_deg": 0.0,
            "start_value": float(start_value),
            "end_value": float(end_value),
            "rate_per_min": float(rate_per_min),
            "duration_sec": float(duration_sec),
            "analysis_chunk_size": int(analysis_chunk_size),
            "demod_periods": int(periods_for_buffer),
            "points_per_channel": int(ai_buffer),
            "hold_final_value": bool(hold_final_value),
            "point_interval_sec": float(min_point_interval_sec),
            "modulation_ramps": ramps,
            "mod_step_fraction": 0.0,
            "ramp_completed": False,
            "completed": False,
            "ao_sample_rate": None,
            "ao_samples": 0,
        }

        def ao_worker():
            """Готовит AO буферы в фоне, запускает прогон и ждёт завершения."""
            try:
                max_ao_samples = 8_000_000
                if float(freq) > 0:
                    base_spp = int(round(400000.0 / max(float(freq), 0.1)))
                    ao_spp = int(max(32, min(256, base_spp)))
                    max_spp_for_duration = int(max_ao_samples / max(duration_sec * max(float(freq), 0.1), 1.0))
                    ao_spp = int(max(32, min(ao_spp, max_spp_for_duration)))
                    ao_sample_rate = int(round(max(float(freq), 0.1) * ao_spp))
                else:
                    ao_spp = 256
                    ao_sample_rate = max(1000, min(int(getattr(settings, "sample_rate", 10000)), 4000))

                total_samples = max(int(round(duration_sec * ao_sample_rate)), ao_spp * 8)
                if total_samples > max_ao_samples:
                    raise ValueError(
                        "Slow heating ramp is too long for the current modulation settings. Increase ramp rate or lower modulation frequency."
                    )
                total_samples = max(ao_spp, (total_samples // ao_spp) * ao_spp)
                t = np.arange(total_samples, dtype=float) / float(ao_sample_rate)

                no_mod_ramps = not any([
                    ramps.get("enable_freq_ramp", False),
                    ramps.get("enable_amp_ramp", False),
                    ramps.get("enable_phase_ramp", False),
                ])
                if float(freq) > 0 and no_mod_ramps:
                    cycle_n = np.arange(ao_spp, dtype=float)
                    base_cycle = offset + amp * np.sin(2.0 * np.pi * (cycle_n / float(ao_spp)))
                    reps = int(np.ceil(total_samples / float(ao_spp)))
                    mod_current = np.tile(base_cycle, reps)[:total_samples]
                    carrier_frequency = float(freq)
                    current_amp = float(amp)
                    current_phase_deg = 0.0
                    mod_step_fraction = 0.0
                else:
                    self.generator = AOStreamSHGenerator(ao_sample_rate)
                    self.generator.set_modulation(freq, amp, offset)
                    ao_chunk_size = max(int(ao_sample_rate * 0.5), ao_spp * 8)
                    self.generator.set_chunk_geometry(ao_chunk_size, duration_sec)
                    self.generator.set_modulation_ramps(
                        final_freq=ramps.get("final_freq", freq),
                        final_amp=ramps.get("final_amp", amp),
                        final_phase_deg=ramps.get("final_phase_deg", 0.0),
                        ramp_steps=ramps.get("ramp_steps", 1),
                        enable_freq_ramp=ramps.get("enable_freq_ramp", False),
                        enable_amp_ramp=ramps.get("enable_amp_ramp", False),
                        enable_phase_ramp=ramps.get("enable_phase_ramp", False),
                        x2_mode=ramps.get("x2_mode", False),
                    )
                    chunks = []
                    last_state = self.generator.current_modulation_values()
                    while self._running:
                        mod_chunk, _ = self.generator.generate_chunk(ao_chunk_size)
                        if mod_chunk is None:
                            break
                        chunks.append(np.asarray(mod_chunk, dtype=float))
                        last_state = self.generator.current_modulation_values()
                        if self.generator.completed:
                            break
                    if not chunks:
                        raise RuntimeError("Failed to prepare slow heating modulation buffer")
                    mod_current = np.concatenate(chunks)
                    total_samples = len(mod_current)
                    t = np.arange(total_samples, dtype=float) / float(ao_sample_rate)
                    carrier_frequency = float(last_state["carrier_freq"])
                    current_amp = float(last_state["amp"])
                    current_phase_deg = float(last_state["phase_deg"])
                    mod_step_fraction = float(last_state["step_fraction"])

                direction = 1.0 if end_value >= start_value else -1.0
                ramp_values = start_value + direction * (abs(rate_per_min) / 60.0) * t
                if direction > 0:
                    ramp_values = np.minimum(ramp_values, end_value)
                else:
                    ramp_values = np.maximum(ramp_values, end_value)

                if mode == "temperature":
                    ch1 = self._temperature_to_voltage_array(ramp_values)
                else:
                    ch1 = np.asarray(ramp_values, dtype=float)

                ch0 = self._heater_current_to_voltage(mod_current)
                zero_samples = max(int(round(min_point_interval_sec * ao_sample_rate)), ao_spp)
                ch0 = np.concatenate((np.zeros(zero_samples, dtype=float), ch0))
                ch1 = np.concatenate((np.zeros(zero_samples, dtype=float), ch1))
                safe = getattr(self.calibration, "safe_voltage", None)
                if safe is not None and np.any(np.abs(ch1) > safe):
                    raise ValueError("Ramp voltage exceeds calibration safe_voltage")

                signals = []
                for ch in range(self.em.ao.channels):
                    if ch == 0:
                        signals.append(ch0)
                    elif ch == 1:
                        signals.append(ch1)
                    else:
                        signals.append(np.zeros(len(ch0), dtype=float))

                self._slow_heating_meta["carrier_frequency"] = carrier_frequency
                self._slow_heating_meta["current_amp"] = current_amp
                self._slow_heating_meta["current_phase_deg"] = current_phase_deg
                self._slow_heating_meta["mod_step_fraction"] = mod_step_fraction
                self._slow_heating_meta["ao_sample_rate"] = int(ao_sample_rate)
                self._slow_heating_meta["ao_samples"] = int(len(ch0))
                self._slow_heating_meta["prestart_zero_sec"] = float(zero_samples / float(ao_sample_rate))
                self._slow_heating_meta["skip_display_points"] = 1
                self._slow_heating_meta["duration_sec"] = float(len(ch0) / float(ao_sample_rate))

                self.em.ao.sample_rate = ao_sample_rate
                self.em.ao.allocate_buffer(len(ch0))
                self.em.ao.fill_buffer(*signals)
                self.em.ao.start_scan()

                total_duration = len(ch0) / float(ao_sample_rate)
                deadline = time.monotonic() + total_duration
                while self._running:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.1, remaining))

                self._slow_heating_meta["ramp_completed"] = True
                self._slow_heating_meta["completed"] = True
            except Exception as exc:
                logger.exception("Slow heating AO stream failed: %s", exc)
                self._slow_heating_meta["error"] = str(exc)
                self._slow_heating_meta["completed"] = True
            finally:
                self._running = False

        self._ao_thread = Thread(target=ao_worker, daemon=True)
        self._ao_thread.start()
        return dict(self._slow_heating_meta)
    def stop_slow_heating(self):
        """Останавливает медленный нагрев и освобождает AO/AI."""
        self._running = False

        if self._ao_timer:
            self._ao_timer.stop()

        self._join_ao_thread()

        try:
            if self.em:
                self.em.ao.stop()
        except Exception:
            pass

        try:
            self.stop_acquisition(owner="slow_heating", force=True)
        except Exception:
            pass

        self.generator = None
        self.reset_ao_outputs()
    def get_slow_heating_meta(self):
        """?????????? ?????? `get_slow_heating_meta`."""
        return dict(getattr(self, "_slow_heating_meta", {}))

    def read_dataSH(self):
        """?????? ?????? `read_dataSH`."""
        return self.read_data()

    def is_fast_heat_running(self):
        """????????? ?????? `is_fast_heat_running`."""
        return bool(getattr(self, "_fast_heat_running", False))


_controller = None


def get_daq_controller():
    """?????????? ?????? `get_daq_controller`."""
    global _controller

    if _controller is None:
        _controller = DAQController()

    return _controller


class DAQDevice:
    """Compatibility proxy that preserves the previous direct-device API."""

    def __init__(self):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self._backend = create_hardware_backend("direct")
        self.device = None
        self.ai_device = None
        self.ao_device = None
        self.descriptor = None

    def connect(self):
        """?????????? ?????? `connect`."""
        self._backend.connect()
        self.device = getattr(self._backend, "device", None)
        self.ai_device = self._backend.get_ai_device()
        self.ao_device = self._backend.get_ao_device()
        self.descriptor = getattr(self._backend, "descriptor", None)

    def get_ai_device(self):
        """?????????? ?????? `get_ai_device`."""
        return self._backend.get_ai_device()

    def get_ao_device(self):
        """?????????? ?????? `get_ao_device`."""
        return self._backend.get_ao_device()

    def disconnect(self):
        """????????? ?????? `disconnect`."""
        self._backend.disconnect()
        self.device = None
        self.ai_device = None
        self.ao_device = None












