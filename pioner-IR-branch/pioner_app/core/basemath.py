import numpy as np
import pandas as pd
import json
import h5py
from datetime import datetime
from pioner_app.core.calibration import Calibration
from bisect import bisect_left

from pioner_app.core.settings import settings

def lockin(Usig, fs, f):

        Usig = Usig - np.mean(Usig)

        t = np.arange(len(Usig)) / fs

        ref_sin = np.sin(2*np.pi*f*t)
        ref_cos = np.cos(2*np.pi*f*t)

        X = np.mean(Usig * ref_cos)
        Y = np.mean(Usig * ref_sin)

        A = 2 * np.sqrt(X**2 + Y**2)
        phase = np.degrees(np.arctan2(Y, X))

        return A, phase


def fft_lockin(signal, fs, f):

        signal = np.asarray(signal, dtype=float)
        if signal.size < 2:
            return 0.0, 0.0

        signal = signal - np.mean(signal)
        window = np.hanning(signal.size)
        windowed = signal * window
        spectrum = np.fft.rfft(windowed)
        freqs = np.fft.rfftfreq(signal.size, d=1.0 / fs)
        idx = int(np.argmin(np.abs(freqs - f)))

        coherent_gain = np.sum(window) / signal.size
        amplitude = 0.0 if coherent_gain == 0 else (2.0 * np.abs(spectrum[idx]) / signal.size) / coherent_gain
        phase = np.degrees(np.angle(spectrum[idx]))
        return float(amplitude), float(phase)


def calcaf_lockin(bufref, bufsig, fclk, fgen, modulation_amp=None, x2_mode=False, addphase=0.0):

        ref = np.asarray(bufref, dtype=float).copy()
        sig = np.asarray(bufsig, dtype=float).copy()

        if ref.size == 0 or sig.size == 0 or ref.size != sig.size or fclk <= 0 or fgen <= 0:
            return 0.0, 0.0

        work_fgen = float(fgen) * (2.0 if x2_mode else 1.0)
        period = int(np.floor(fclk / work_fgen + 0.5))
        if period < 4:
            return 0.0, 0.0

        xp = int(np.floor(1000.0 / period))
        xp = min(max(xp, 1), 100)
        xperiod = int(np.floor(xp * fclk / work_fgen + 0.5))
        if xperiod <= 1:
            return 0.0, 0.0

        nperiods = int(np.floor(len(ref) / fclk * work_fgen))
        fullperiods = int(np.floor(nperiods * fclk / work_fgen + 0.5))
        fullperiods = min(fullperiods, len(ref))
        if nperiods < 3 or fullperiods <= period:
            return 0.0, 0.0

        ref_mean = np.mean(ref[:fullperiods])
        sig_mean = np.mean(sig[:fullperiods])
        ref -= ref_mean
        sig -= sig_mean

        if x2_mode:
            ref = ref * ref
            ref -= np.mean(ref[:fullperiods])

        if modulation_amp is not None and float(modulation_amp) > 0:
            refmax = (float(modulation_amp) ** 2) / 2.0 if x2_mode else float(modulation_amp)
        else:
            refmax = (float(np.max(ref)) - float(np.min(ref))) / 2.0 if ref.size else 0.0

        if refmax > 0.0:
            ref = ref / refmax

        xphasestep = 2.0 * np.pi * work_fgen / fclk / xp
        mult = np.zeros(xperiod, dtype=float)

        for i in range(xperiod):
            ixp = float(i) / xp
            flixp = int(np.floor(ixp))
            fxi = ixp - flixp
            acc = 0.0
            count = 0
            for j in range(max(fullperiods - period, 0)):
                if xp == 1:
                    idx = i + j
                    if idx >= sig.size:
                        break
                    acc += ref[j] * sig[idx]
                else:
                    ii = j + flixp
                    if ii < 0:
                        ii = 0
                    if ii > sig.size - 1:
                        ii = sig.size - 1
                    v1 = sig[ii]
                    v2 = sig[ii + 1] if ii < sig.size - 1 else v1
                    vx = v1 + (v2 - v1) * fxi
                    acc += ref[j] * vx
                count += 1
            mult[i] = acc / count if count else 0.0

        imax = int(np.argmax(mult))
        amax = float(np.max(mult))
        amin = float(np.min(mult))
        offset1 = float(np.mean(mult))
        ampl0 = (amax - amin) / 2.0
        phase0 = imax * xphasestep
        phase1 = phase0
        ampl1 = ampl0
        icn = xperiod // 2
        fit_ok = False

        if ampl0 > 0.0:
            work = np.roll(mult, -imax)
            work = np.roll(work, icn)
            phase1 = 0.0
            errfmin = 0.0001
            erramin = abs(ampl0 / 1000.0)
            erromin = abs(ampl0 / 1000.0)
            fit_ok = True
            for _ in range(50):
                errf = 0.0
                erro = 0.0
                for i in range(icn, xperiod):
                    errf += work[i] - ampl1 * np.cos(-phase1 + (i - icn) * xphasestep) - offset1
                erro += errf
                for i in range(0, icn):
                    errf -= work[i] - ampl1 * np.cos(-phase1 + (i - icn) * xphasestep) - offset1
                erro -= errf
                errf /= (xperiod * ampl0)
                phase1 = (phase1 + errf) % (2.0 * np.pi)
                erro /= xperiod
                offset1 += erro * 0.3

                erra = 0.0
                q1 = xperiod // 4
                q3 = (xperiod * 3) // 4
                for i in range(q1, q3):
                    erra += work[i] - ampl1 * np.cos(-phase1 + (i - icn) * xphasestep) - offset1
                for i in range(0, q1):
                    erra -= work[i] - ampl1 * np.cos(-phase1 + (i - icn) * xphasestep) - offset1
                for i in range(q3, xperiod):
                    erra -= work[i] - ampl1 * np.cos(-phase1 + (i - icn) * xphasestep) - offset1
                erra /= xperiod
                ampl1 += erra * 0.5

                if abs(errf) < errfmin and abs(erra) < erramin and abs(erro) < erromin:
                    break
                if abs(errf) > 10.0 or abs(erra) > 10.0 or abs(erro) > 10.0:
                    fit_ok = False
                    break

            phase1 = imax * xphasestep + phase1

        if not fit_ok:
            phase1 = phase0
            ampl1 = ampl0

        phase_deg = np.degrees(phase1) - float(addphase)
        while phase_deg > 180.0:
            phase_deg -= 360.0
        while phase_deg < -180.0:
            phase_deg += 360.0

        amplitude = 2.0 * float(ampl1)
        return amplitude, float(phase_deg)
    
def voltage_to_temperature( voltage: np.array, calibration: Calibration) -> np.array:
        voltage = np.asarray(voltage)  # <--- РґРѕР±Р°РІСЊС‚Рµ СЌС‚Сѓ СЃС‚СЂРѕРєСѓ
        volt = voltage.copy()
        volt[volt < 0] = 0
        volt[volt > calibration.safe_voltage] = calibration.safe_voltage
        temp = calibration.theater0 * volt + calibration.theater1 * (volt**2) + calibration.theater2 * (volt**3)
        return temp


    # TODO: think maybe to create a T-V (and vice versa) converter class
def temperature_to_voltage(temp, calibration):

    temp = np.atleast_1d(np.asarray(temp, dtype=float))

    safe_voltage = float(max(getattr(calibration, "safe_voltage", 0.0), 0.0))
    if safe_voltage <= 0.0:
        voltage = np.zeros(len(temp), dtype=float)
        return float(voltage[0]) if voltage.size == 1 else voltage

    grid_size = max(20001, int(round(safe_voltage * 5000)))
    volt_calib = np.linspace(0.0, safe_voltage, grid_size, dtype=float)
    temp_calib = np.asarray(voltage_to_temperature(volt_calib, calibration), dtype=float)

    order = np.argsort(temp_calib, kind="mergesort")
    temp_sorted = temp_calib[order]
    volt_sorted = volt_calib[order]

    temp_sorted, unique_idx = np.unique(temp_sorted, return_index=True)
    volt_sorted = volt_sorted[unique_idx]

    if temp_sorted.size == 0:
        voltage = np.zeros(len(temp), dtype=float)
    elif temp_sorted.size == 1:
        voltage = np.full(len(temp), volt_sorted[0], dtype=float)
    else:
        temp_clamped = np.clip(temp, temp_sorted[0], temp_sorted[-1])
        voltage = np.interp(temp_clamped, temp_sorted, volt_sorted)

    voltage = np.clip(voltage, 0.0, safe_voltage)

    if voltage.size == 1:
        return float(voltage[0])

    return voltage

class DataProcessor:

    def __init__(self, calibration=None, sample_rate=None, precision=6):

        self.calibration = calibration  # в†ђ С‚РµРїРµСЂСЊ СЌС‚Рѕ Calibration (РќР• em)
        self.sample_rate = sample_rate or settings.sample_rate
        self.precision = precision

    # =====================================================
    # SERVICE
    # =====================================================

    def _round(self, arr):
        return None if arr is None else np.round(arr, self.precision)

    def _time_axis(self, n, mode="fast"):
        t = np.arange(n) / self.sample_rate
        return t * 1000.0 if mode == "fast" else t

    def _ensure_array(self, arr, length):
        if arr is None:
            return np.zeros(length)
        if np.isscalar(arr):
            return np.full(length, arr)
        return np.asarray(arr)

    def _match_length(self, arr, length):
        if arr is None:
            return np.zeros(length)

        arr = np.asarray(arr)

        if len(arr) > length:
            return arr[:length]

        if len(arr) < length:
            return np.pad(arr, (0, length - len(arr)), mode="edge")

        return arr

    # =====================================================
    # FAST HEAT
    # =====================================================

    def process_fast_heat(self, raw_data, calibration=None, ref_signal=None):

        raw_data = np.asarray(raw_data)
        n = len(raw_data)

        ########################################
        # RAW
        ########################################

        Uref = raw_data[:, 0]

        ########################################
        # CALIBRATED DATA (рџ”Ґ РџР РРҐРћР”РРў РЎРќРђР РЈР–Р)
        ########################################

        temp = temp_hr = Thtr = Taux = None
        if calibration is not None:
            self.calibration = calibration
            
        if self.calibration:
            calib_data = self.calibration.apply_fh_cal(raw_data)
            temp = calib_data[:, 0]
            temp_hr = calib_data[:, 1]
            Ihtr=calib_data[:,2]
            Thtr = calib_data[:, 3]
            Taux = calib_data[:, 4]

        ########################################
        # DERIVED
        ########################################

        '''Ihtr = None
        if self.calibration:
            Ihtr = self.calibration.ihtr0 + Uref * self.calibration.ihtr1
        '''
        ########################################
        # TIME
        ########################################

        t = self._time_axis(n, mode="fast")

        ########################################
        # REF
        ########################################

        ref_signal = self._match_length(ref_signal, n)
        print(ref_signal[12000:12050])
        ########################################
        # RESULT
        ########################################

        return {
            "time(ms)": self._round(t),
            "temp": self._round(self._ensure_array(temp, n)),
            "temp-hr": self._round(self._ensure_array(temp_hr, n)),
            "Ref": self._round(ref_signal),
            "Ihtr": self._round(self._ensure_array(Ihtr, n)),
            "Thtr": self._round(self._ensure_array(Thtr, n)),
            "Taux": self._round(self._ensure_array(Taux, n)),
        }

    # =====================================================
    # SLOW HEATING
    # =====================================================


    def analyze_slow_heating_chunk(self, data, frequency, method="lockin", periods=5, modulation_amp=None, x2_mode=False, addphase=0.0):

        raw = np.asarray(data, dtype=float)
        if raw.ndim == 1:
            raw = raw.reshape(1, -1)
        if raw.size == 0 or raw.shape[1] < 6:
            return None

        if frequency <= 0:
            frequency = 0.0

        if frequency > 0:
            samples_per_period = max(1, int(round(self.sample_rate / frequency)))
            requested_periods = max(int(periods), 1)
            available_periods = max(1, len(raw) // samples_per_period)
            effective_periods = min(requested_periods, available_periods)
            needed = max(samples_per_period * effective_periods, samples_per_period)
            window = raw[-min(len(raw), needed):]
            full_periods = len(window) // samples_per_period
            if full_periods >= 2:
                full_samples = full_periods * samples_per_period
                window = window[-full_samples:]
                window = window[samples_per_period:]
            elif full_periods == 1:
                window = window[-samples_per_period:]
        else:
            samples_per_period = len(raw)
            window = raw.copy()

        if window.size == 0:
            return None

        cal = self.calibration
        Uref = np.asarray(window[:, 0], dtype=float)
        Umod_mV = np.asarray(window[:, 1], dtype=float) / 121.0 * 1000.0
        Uaux = np.asarray(window[:, 3], dtype=float)
        Utpl_mV = np.asarray(window[:, 4], dtype=float) / 11.0 * 1000.0
        Uhtr_mV = np.asarray(window[:, 5], dtype=float) * 1000.0
        utpl_raw_mean = float(np.mean(Utpl_mV)) if len(Utpl_mV) else 0.0
        uhtr_raw_mean = float(np.mean(Uhtr_mV)) if len(Uhtr_mV) else 0.0
        ihtr_raw_mean = float(np.mean(Uref)) if len(Uref) else 0.0

        Taux = float(np.mean(Uaux) * 100.0)
        if Taux < -12.0:
            Taux = 2.6843 + 1.2709 * Taux + 0.0042867 * Taux * Taux + 3.4944e-05 * Taux * Taux * Taux

        ref_signal = Uref
        if cal is not None:
            ax_mod = Umod_mV + cal.utpl0
            temp_hr_trace = cal.ttpl0 * ax_mod + cal.ttpl1 * (ax_mod ** 2)

            ax_tpl = Utpl_mV + cal.utpl0
            ttpl_trace = cal.ttpl0 * ax_tpl + cal.ttpl1 * (ax_tpl ** 2) + Taux

            ihtr_trace = cal.ihtr0 + Uref * cal.ihtr1
            ref_signal = ihtr_trace
            uabs_raw = Uhtr_mV - Uref * 1000.0
            uabs_raw = np.maximum(uabs_raw, 0.0)
            uhtr_trace = (uabs_raw + cal.uhtr0) * cal.uhtr1

            ihtr_mean = float(np.mean(ihtr_trace)) if len(ihtr_trace) else 0.0
            uhtr_mean = float(np.mean(uhtr_trace)) if len(uhtr_trace) else 0.0
            ttpl = float(np.mean(ttpl_trace)) if len(ttpl_trace) else 0.0
            uabs_raw_mean = float(np.mean(uabs_raw)) if len(uabs_raw) else 0.0

            if ihtr_mean > 0.001:
                rhtr = uhtr_mean / ihtr_mean
                thtr = cal.thtr0 + cal.thtr1 * (rhtr + cal.thtrcorr) + cal.thtr2 * ((rhtr + cal.thtrcorr) ** 2)
            else:
                rhtr = 0.0
                thtr = 0.0

            valid = ihtr_trace > 0.0
            if np.any(valid):
                d_u = uhtr_trace[valid] - uhtr_mean
                d_i = ihtr_trace[valid] - ihtr_mean
                acurms = float(np.sqrt(np.mean(d_u ** 2)))
                acirms = float(np.sqrt(np.mean(d_i ** 2)))
            else:
                acurms = 0.0
                acirms = 0.0

            if acirms > 0.0 and frequency > 0:
                rhtrd = acurms / acirms
                thtrd = cal.thtrd0 + cal.thtrd1 * (rhtrd + cal.thtrdcorr) + cal.thtrd2 * ((rhtrd + cal.thtrdcorr) ** 2)
            else:
                rhtrd = 0.0
                thtrd = 0.0

            power = abs(uhtr_mean * ihtr_mean) / 1e6
            mod_signal = temp_hr_trace
            amplitude_unit = "C"
            demod_signal_name = "temperature"
        else:
            mod_signal = Umod_mV
            ttpl = float(np.mean(Utpl_mV)) if len(Utpl_mV) else 0.0
            thtr = 0.0
            thtrd = 0.0
            ihtr_mean = ihtr_raw_mean
            uhtr_mean = uhtr_raw_mean
            uabs_raw_mean = uhtr_raw_mean
            power = 0.0
            rhtr = 0.0
            rhtrd = 0.0
            amplitude_unit = "mV"
            demod_signal_name = "voltage"

        if method == "fft":
            amplitude, phase = fft_lockin(mod_signal, self.sample_rate, frequency)
        else:
            amplitude, phase = calcaf_lockin(
                ref_signal,
                mod_signal,
                self.sample_rate,
                frequency,
                modulation_amp=modulation_amp,
                x2_mode=x2_mode,
                addphase=addphase,
            )

        return {
            "UtplRaw": float(utpl_raw_mean),
            "Ttpl": float(ttpl),
            "UhtrRaw": float(uhtr_raw_mean),
            "Uhtr": float(uhtr_mean),
            "IhtrRaw": float(ihtr_raw_mean),
            "Ihtr": float(ihtr_mean),
            "UabsRaw": float(uabs_raw_mean),
            "Rhtr": float(rhtr),
            "Thtr": float(thtr),
            "Rhtrd": float(rhtrd),
            "Thtrd": float(thtrd),
            "Taux": float(Taux),
            "power": float(power),
            "amplitude": float(amplitude),
            "phase": float(phase),
            "amplitude_unit": amplitude_unit,
            "demod_signal_name": demod_signal_name,
            "samples": int(len(window)),
        }

    def process_slow_heat(self, raw_data, modulation_params=None):

        raw_data = np.array(raw_data)

        Uref = raw_data[:, 0]
        Umod = raw_data[:, 1]
        Uhtr = raw_data[:, 2]
        Uaux = raw_data[:, 3]
        Utpl = raw_data[:, 4]
        Uhtrabs = raw_data[:, 5]

        ########################################
        # РљРђР›РР‘Р РћР’РљРђ
        ########################################

        temp = None
        Thtr = None
        Thtrd = None
        Taux = None
        Ihtr = None

        if self.calibration:
            calib_data = self.calibration.apply_fh_cal(raw_data)

            temp = calib_data[:, 0]
            Thtr = calib_data[:, 2]
            Taux=calib_data[:, 2]

            Ihtr = self.calibration.calibration.ihtr0 + Uref * self.calibration.calibration.ihtr1

        ########################################
        # TIME
        ########################################

        t = self._time_axis(len(raw_data), mode="slow")

        ########################################
        # РњРћР”РЈР›РЇР¦РРЇ
        ########################################

        if modulation_params:
            freq = modulation_params.get("frequency", 0)
            ampl = modulation_params.get("amplitude", 0)
            offset = modulation_params.get("offset", 0)
        else:
            freq = ampl = offset = 0

        ########################################
        # DERIVED
        ########################################

        resistance = np.divide(Uhtr, Ihtr, out=np.zeros_like(Uhtr), where=Ihtr != 0)
        power = Uhtr * Ihtr

        ########################################
        # PHASE / AMPLITUDE (Р·Р°РіР»СѓС€РєР°)
        ########################################

        amplitude = np.abs(Umod)
        phase = np.zeros_like(Umod)

        ########################################
        # РЎР›РћР’РђР Р¬
        ########################################

        data_dict = {
            "time(s)": self._round(t),
            "amplitude": self._round(amplitude),
            "phase": self._round(phase),
            "Ttpl": self._round(temp),
            "UhtrG": self._round(Uhtr),
            "Ihtr": self._round(Ihtr),
            "Thtr": self._round(Thtr),
            "Thtrd": self._round(Thtrd if Thtrd is not None else Thtr),
            "Taux": self._round(Taux if np.isscalar(Taux) else np.full_like(t, Taux)),
            "frequency": freq,
            "ModAmpl": ampl,
            "ModOfset": offset,
            "Resistance": self._round(resistance),
            "M-power": self._round(power)
        }

        return data_dict

    # =====================================================
    # SAVE
    # =====================================================

    def save(self, data_dict, folder="results", name_prefix="exp", fmt="hdf5", calibration=None, settings_obj=None):

        import os
        os.makedirs(folder, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        base = f"{folder}/{name_prefix}_{timestamp}"

        normalized = {}
        max_len = 0
        for key, value in data_dict.items():
            if np.isscalar(value):
                normalized[key] = value
                continue
            arr = np.asarray(value)
            normalized[key] = arr
            if arr.ndim > 0:
                max_len = max(max_len, len(arr))

        for key, value in list(normalized.items()):
            if np.isscalar(value):
                normalized[key] = np.full(max_len or 1, value)

        df = pd.DataFrame(normalized)

        if fmt == "csv":
            path = base + ".csv"
            df.to_csv(path, index=False)

        elif fmt == "json":
            path = base + ".json"
            df.to_json(path, orient="records", indent=2)

        elif fmt in ("hdf5", "h5"):
            path = base + ".h5"
            with h5py.File(path, "w") as f:
                data_group = f.create_group("data")
                for k, v in normalized.items():
                    data_group.create_dataset(k, data=np.asarray(v))

                calib_obj = calibration or self.calibration
                if calib_obj is not None and hasattr(calib_obj, "to_dict"):
                    f.create_dataset("calibration", data=json.dumps(calib_obj.to_dict(), ensure_ascii=False))

                settings_payload = settings_obj
                if settings_payload is None:
                    settings_payload = {
                        "sample_rate": getattr(settings, "sample_rate", None),
                        "mod_freq": getattr(settings, "mod_freq", None),
                        "mod_amp": getattr(settings, "mod_amp", None),
                        "mod_offset": getattr(settings, "mod_offset", None),
                        "data_path": getattr(settings, "data_path", None),
                        "calibration_path": getattr(settings, "calibration_path", None),
                    }
                f.create_dataset("settings", data=json.dumps(settings_payload, ensure_ascii=False))

        else:
            raise ValueError("Unsupported format")

        return path
    
    def _safe_array(self, arr, length):
        if arr is None:
            return np.zeros(length)
        return np.array(arr)
    
    def _match_length(self, arr, length):
        if arr is None:
            return np.zeros(length)

        arr = np.array(arr)

        if len(arr) > length:
            return arr[:length]

        if len(arr) < length:
            return np.pad(arr, (0, length - len(arr)), mode='edge')

        return arr
    
    def _ensure_array(self, arr, length):
        if arr is None:
            return np.zeros(length)

        if np.isscalar(arr):
            return np.full(length, arr)

        return np.array(arr)

