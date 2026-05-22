import logging
import time
import numpy as np

try:
    from uldaq import ScanStatus
except Exception:
    class ScanStatus:
        IDLE = "IDLE"

from pioner_app.hardware.ai_device import AIDevice
from pioner_app.hardware.ao_device import AODevice, AOGenerator

from pioner_app.core.settings import settings
import pioner_app.core.calibration
import json



logger = logging.getLogger(__name__)


class ExperimentManager:

    def __init__(self, daq_device, scope=None, calibration=None):

        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.daq = daq_device
        self.scope = scope
        self.calibration = calibration
        self.last_ao_signals = None

        self.ai = AIDevice(self.daq.get_ai_device())
        self.ao = AODevice(self.daq.get_ao_device())
    

    def run(self, profile_path, progress_cb=None):

        """????????? ?????? `run`."""
        logger.info("Starting experiment")

        ################################
        # LOAD PROFILE
        ################################

        profile = ExperimentProfile(
            profile_path,
            channels=self.ao.channels
        )

        signals, samples = profile.build()

        # рџ”Ґ РЎРћРҐР РђРќРЇР•Рњ AO РЎРР“РќРђР›Р«
        self.last_ao_signals = signals

        logger.info(f"Experiment samples: {samples}")

        ################################
        # ALLOCATE BUFFERS
        ################################

        self.ao.allocate_buffer(samples)
        self.ai.allocate_buffer(samples)

        ################################
        # FILL AO BUFFER
        ################################

        self.ao.fill_buffer(*signals)

        ################################
        # START SCANS
        ################################

        logger.info("Starting AI scan")
        self.ai.start_scan()

        logger.info("Starting AO scan")
        self.ao.start_scan()

        ################################
        # REALTIME LOOP
        ################################

        last_progress = 0

        

        while True:

            status, progress = self.ai.get_progress()

            percent = progress / samples * 100

            print(f"\rProgress {percent:6.2f}%", end="", flush=True)

            # вњ… Р’РћРў РўРђРљ РџР РђР’РР›Р¬РќРћ
            if progress_cb:
                progress_cb(int(percent))
            

            ################################
            # NEW DATA AVAILABLE
            ################################

            if progress > last_progress:

                raw = self.ai.read_available_data(progress)

                ################################
                # TIME AXIS
                ################################

                t = np.arange(len(raw)) / settings.sample_rate





                last_progress = progress

            ################################

            if status == ScanStatus.IDLE:
                break
            
            time.sleep(0.02)
        self.ai.stop()    

        print()

        logger.info("Experiment finished")

        ################################
        # STOP DEVICES
        ################################

        try:

            self.ai.stop()

        except Exception:

            logger.warning("AI stop failed")

        try:

            self.ao.stop()

        except Exception:

            logger.warning("AO stop failed")

        ################################
        # RETURN DATA
        ################################

        final_data = np.array(self.ai.buffer)

        final_data = final_data.reshape(-1, self.ai.channels)

        return final_data
    def start_continuous(self, points_per_channel=1000):

        """????????? ?????? `start_continuous`."""
        logger.info("Starting continuous acquisition")

        self.points_per_channel = points_per_channel

        self.ai.allocate_buffer(points_per_channel)

        self.ai.start_scan_continious()

        self._last_index = 0


    def _read_continuous_window(self, count, advance=False):

        """?????? ?????? `read_continuous_window`."""
        if not hasattr(self, "_last_index"):
            return None

        status, progress = self.ai.get_progress()
        available = progress - self._last_index if advance else progress
        if available <= 0:
            return None

        capacity = int(getattr(self, "points_per_channel", 0) or 0)
        if capacity <= 0:
            return None

        count = min(int(count), int(available), capacity)
        if count <= 0:
            return None

        flat = np.array(self.ai.buffer[:capacity * self.ai.channels])
        if flat.size == 0:
            if advance:
                self._last_index = progress
            return None

        raw = flat.reshape(capacity, self.ai.channels)
        start_total = progress - count
        start = int(start_total % capacity)
        end = int(progress % capacity)

        if count >= capacity:
            chunk = raw.copy()
        elif start < end:
            chunk = raw[start:end].copy()
        else:
            chunk = np.vstack((raw[start:], raw[:end])).copy()

        if advance:
            self._last_index = progress
        if chunk.size == 0:
            return None
        return chunk

    def read_continuous(self):
        """?????? ?????? `read_continuous`."""
        if not hasattr(self, "_last_index"):
            return None

        status, progress = self.ai.get_progress()
        delta = progress - self._last_index
        if delta <= 0:
            return None

        return self._read_continuous_window(delta, advance=True)

    def peek_continuous(self, count=None):
        """???????? ?????? `peek_continuous`."""
        capacity = int(getattr(self, "points_per_channel", 0) or 0)
        if capacity <= 0:
            return None
        if count is None:
            count = capacity
        return self._read_continuous_window(count, advance=False)

    def stop_continuous(self):

        """????????????? ?????? `stop_continuous`."""
        logger.info("Stopping continuous acquisition")

        try:
            self.ai.stop()
        except Exception as e:
            logger.warning(f"AI stop failed: {e}")
    
    def acquire_signals_diag(self, duration_sec=1.0):

        """???????? ?????? `acquire_signals_diag`."""
        logger.info("Diagnostic acquisition start")

        self.start_continuous(points_per_channel=1000)

        start_time = time.time()
        collected = []

        while time.time() - start_time < duration_sec:

            result = self.read_continuous()

            if result is None:
                time.sleep(0.01)
                continue

            collected.append(result)

            time.sleep(0.01)

        self.stop_continuous()

        if len(collected) == 0:
            return None

        data = np.vstack(collected)

        return data
        
    def start_ao_continuous_mod(self, freq, ampl_mA, offset_mA,
                            duration_sec=30, channel=0, sample_rate=10000, phase_deg=0.0):

        """????????? ?????? `start_ao_continuous_mod`."""
        logger.info(f"Starting AO continuous on channel {channel}")

        try:
            self.ao.stop()
        except Exception:
            pass

        freq = float(freq)
        phase_rad = np.deg2rad(float(phase_deg))

        if freq > 0.0:
            samples_per_period = int(np.floor(400000.0 / freq + 0.5))
            samples_per_period = min(max(samples_per_period, 32), 1024)
            ao_sample_rate = max(int(round(freq * samples_per_period)), int(sample_rate))
            target_seconds = max(float(duration_sec), 30.0)
            max_samples = 500000
            samples = max(int(round(target_seconds * ao_sample_rate)), samples_per_period * 32)
            samples = min(samples, max_samples)
            samples = max(samples_per_period, (samples // samples_per_period) * samples_per_period)
        else:
            ao_sample_rate = int(sample_rate)
            samples = max(int(max(float(duration_sec), 30.0) * ao_sample_rate), 4096)

        t = np.arange(samples, dtype=float) / float(ao_sample_rate)
        i_signal = offset_mA + ampl_mA * np.sin(2 * np.pi * freq * t + phase_rad)
        v_signal = self._current_to_voltage(i_signal)

        if hasattr(self.calibration, "safe_voltage"):
            if np.any(np.abs(v_signal) > self.calibration.safe_voltage):
                raise ValueError("AO voltage exceeds safe limit")

        signals = []
        for ch in range(self.ao.channels):
            if ch == channel:
                signals.append(v_signal)
            else:
                signals.append(np.zeros_like(v_signal))

        self.ao.sample_rate = ao_sample_rate
        self.ao.allocate_buffer(samples)
        self.ao.fill_buffer(*signals)
        self.ao.start_scan_continious()

        logger.info(f"AO continuous started: fs={ao_sample_rate} Hz, samples={samples}")

    def stop_ao_continuous(self):

        """????????????? ?????? `stop_ao_continuous`."""
        logger.info("Stopping AO continuous")

        try:
            self.ao.stop()
        except Exception as e:
            logger.warning(f"AO stop failed: {e}")
    
    def _current_to_voltage(self, i_mA):

        """???????? ?????? `current_to_voltage`."""
        calib = self.calibration

        i = i_mA / 1000.0  # РјРђ в†’ Рђ

        return (i - calib.ihtr0) / calib.ihtr1
    

    def _ms_to_samples(self, duration_ms, sample_rate):

        """Converts fast-heat step duration from ms to integer samples."""
        duration_ms = float(duration_ms)
        sample_rate = float(sample_rate)
        if duration_ms <= 0 or sample_rate <= 0:
            return 1
        return max(1, int(round(duration_ms * sample_rate / 1000.0)))

    def _build_fast_heat_step(self, step, sample_rate):

        """Builds a single fast-heat AO step on an explicit time grid."""
        step_type = str(step["type"])
        samples = self._ms_to_samples(step.get("duration", 0.0), sample_rate)

        if step_type == "isotherm":
            return np.full(samples, float(step["value"]), dtype=float)

        if step_type == "ramp":
            start = float(step["start"])
            stop = float(step["stop"])
            if samples == 1:
                return np.array([stop], dtype=float)
            return np.linspace(start, stop, samples, endpoint=True, dtype=float)

        if step_type == "sine":
            frequency = float(step.get("frequency", 0.0))
            amplitude = float(step.get("amplitude", 0.0))
            offset = float(step.get("offset", 0.0))
            t = np.arange(samples, dtype=float) / float(sample_rate)
            return offset + amplitude * np.sin(2.0 * np.pi * frequency * t)

        raise ValueError(f"Unknown fast-heat step type: {step_type}")

    def build_fast_heat_signals(self, profile_dict, sample_rate=None):

        """Builds a fast-heating AO profile directly from the in-memory dict."""
        sample_rate = int(sample_rate or settings.sample_rate)
        channel_profiles = dict(profile_dict.get("channels", {}))
        signals = []

        for ch in range(self.ao.channels):
            steps = channel_profiles.get(str(ch), []) or []
            channel_chunks = []
            for step in steps:
                channel_chunks.append(self._build_fast_heat_step(step, sample_rate))
            if channel_chunks:
                signal = np.concatenate(channel_chunks).astype(np.float64, copy=False)
            else:
                signal = np.zeros(1, dtype=np.float64)
            signals.append(signal)

        post = profile_dict.get("post_hold") or {}
        if post.get("enabled"):
            hold_samples = self._ms_to_samples(post.get("duration", 0.0), sample_rate)
            channels_cfg = post.get("channels", {}) or {}
            for ch in range(self.ao.channels):
                hold_value = float(channels_cfg.get(str(ch), signals[ch][-1]))
                hold = np.full(hold_samples, hold_value, dtype=np.float64)
                signals[ch] = np.concatenate((signals[ch], hold))

        max_len = max(len(signal) for signal in signals)
        for idx, signal in enumerate(signals):
            if len(signal) < max_len:
                pad = np.full(max_len - len(signal), float(signal[-1]), dtype=np.float64)
                signals[idx] = np.concatenate((signal, pad))

        return signals, int(max_len), {"sample_rate": sample_rate, "duration_sec": max_len / float(sample_rate)}

    def _run_finite_profile(self, signals, samples, sample_rate, progress_cb=None):

        """Runs a finite synchronized AI/AO scan for fast heating."""
        self.last_ao_signals = signals
        self.ao.sample_rate = int(sample_rate)
        self.ai.sample_rate = int(sample_rate)

        self.ao.allocate_buffer(samples)
        self.ai.allocate_buffer(samples)
        self.ao.fill_buffer(*signals)

        logger.info("Starting AI scan")
        self.ai.start_scan()
        logger.info("Starting AO scan")
        self.ao.start_scan()

        requested_rate = int(sample_rate)
        actual_ai_rate = float(getattr(self.ai, "actual_sample_rate", self.ai.sample_rate))
        actual_ao_rate = float(getattr(self.ao, "actual_sample_rate", self.ao.sample_rate))
        logger.info("Fast heat scan rates: requested=%s Hz, AI actual=%s Hz, AO actual=%s Hz", requested_rate, actual_ai_rate, actual_ao_rate)
        print(f"Fast heat scan rates: requested={requested_rate} Hz, AI actual={actual_ai_rate:.3f} Hz, AO actual={actual_ao_rate:.3f} Hz")

        while True:
            status, progress = self.ai.get_progress()
            percent = 0.0 if samples <= 0 else min(100.0, (progress / float(samples)) * 100.0)
            if progress_cb:
                progress_cb(int(percent))
            if status == ScanStatus.IDLE:
                break
            time.sleep(0.02)

        try:
            self.ai.stop()
        except Exception:
            logger.warning("AI stop failed")

        try:
            self.ao.stop()
        except Exception:
            logger.warning("AO stop failed")

        final_data = np.array(self.ai.buffer)
        final_data = final_data.reshape(-1, self.ai.channels)
        return final_data

    def run_fast_heat_profile(self, profile_dict, progress_cb=None):

        """Runs fast heating via a dedicated builder/runner path with explicit timing."""
        signals, samples, meta = self.build_fast_heat_signals(profile_dict, sample_rate=settings.sample_rate)
        logger.info("Fast heat profile prepared: fs=%s Hz, samples=%s, duration=%.3f s", meta["sample_rate"], samples, meta["duration_sec"])
        return self._run_finite_profile(signals, samples, meta["sample_rate"], progress_cb=progress_cb)

    def run_profile(self, profile_dict, progress_cb=None):

        """Backward-compatible generic profile runner."""
        return self.run_fast_heat_profile(profile_dict, progress_cb=progress_cb)
    

    def get_ref_signal(self, channel=1):
        """?????????? ?????? `get_ref_signal`."""
        if self.last_ao_signals is None:
            return None
        return self.last_ao_signals[channel]
    



    def SH_step(self, value, freq, ampl_mA, offset_mA,
                        ):

        

        # рџ”Ґ Р’РђР–РќРћ: РѕСЃС‚Р°РЅРѕРІРёС‚СЊ РµСЃР»Рё СѓР¶Рµ СЂР°Р±РѕС‚Р°РµС‚
        """???????? ?????? `SH_step`."""
        try:
            self.ao.stop()
        except:
            pass

        gen= AOGenerator()

        # в†’ РЅР°РїСЂСЏР¶РµРЅРёРµ
        sine_signal = gen.sine_modulation(0,freq, ampl_mA, offset_mA)
        voltsignal=gen.set_voltage(1,value,freq)
        # Р±РµР·РѕРїР°СЃРЅРѕСЃС‚СЊ
        if hasattr(self.calibration, "safe_voltage"):
            if np.any(np.abs(voltsignal) > self.calibration.safe_voltage):
                raise ValueError("AO voltage exceeds safe limit")

    ''' # рџ”Ґ С„РѕСЂРјРёСЂСѓРµРј РїРѕ РєР°РЅР°Р»Р°Рј
        signals = 



        # Р±СѓС„РµСЂ
        self.ao.sample_rate = sample_rate
        self.ao.allocate_buffer(samples)
        self.ao.fill_buffer(*signals)

        self.ao.start_scan_continious()

        logger.info("AO continuous started")'''







class ExperimentProfile:

    def __init__(self, path, channels):

        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.path = path
        self.channels = channels

        with open(path) as f:
            self.profile = json.load(f)

    def build(self):

        """???????? ?????? `build`."""
        logger.info(f"Loading experiment profile {self.path}")

        gen = AOGenerator(self.channels)

        channel_profiles = self.profile["channels"]

        for ch_str, steps in channel_profiles.items():

            channel = int(ch_str)

            for step in steps:

                step_type = step["type"]

                if step_type == "ramp":

                    gen.ramp(
                        channel=channel,
                        duration=step["duration"],
                        start=step["start"],
                        stop=step["stop"]
                    )

                elif step_type == "isotherm":

                    gen.isotherm(
                        channel=channel,
                        duration=step["duration"],
                        value=step["value"]
                    )

                elif step_type == "sine":

                    gen.sine(
                        channel=channel,
                        duration=step["duration"],
                        frequency=step["frequency"],
                        amplitude=step["amplitude"],
                        offset=step.get("offset", 0)
                    )

                else:

                    raise ValueError(
                        f"Unknown step type {step_type}"
                    )

        signals, samples = gen.build()

        logger.info(f"AO signal length {samples} samples")

        ################################
        # POST HOLD
        ################################

        post = self.profile.get("post_hold")

        if post and post["enabled"]:

                duration = post["duration"]

                hold_samples = int(duration * settings.sample_rate / 1000)

                logger.info(f"Post hold {duration} ms")

                for ch in range(self.channels):

                    value = post["channels"].get(str(ch), signals[ch][-1])

                    hold = np.ones(hold_samples) * value

                    signals[ch] = np.concatenate((signals[ch], hold))

                samples = len(signals[0])

        logger.info(f"Experiment length: {samples} samples")

        return signals, samples
        



