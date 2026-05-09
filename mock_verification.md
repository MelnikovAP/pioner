# Mock-DAQ pipeline verification — MVP readiness

This document is the verification checklist for the three calorimetry modes
(`FastHeat`, `SlowMode`, `IsoMode`) running on the pure-Python `mock_uldaq`
backend. It covers what the mock proves, what the mock cannot prove, and how
to exercise the system manually before touching real hardware.

All commands assume the repo root and the dev venv:

```bash
PYTHONPATH=src .venv/bin/python ...
PYTHONPATH=src .venv/bin/pytest tests/
```

`uldaq` raises `OSError` on macOS (no `libuldaq.dylib`), so the mock backend is
activated automatically — no env var or flag required.

---

## 1. What is verified to work on the mock

### 1.1 FastHeat
- AO `ch1` triangular profile (0→1→0 V over 1 s) is produced with
  `sample_rate × seconds = 20000` samples. The midpoint reads `0.99995` V
  rather than exactly `1.0` because `np.linspace` does not place a sample at
  `t = 500 ms` exactly — this is a normal interpolation artifact, not a bug.
- Half-buffer flip in `_collect_finite_ai` collects exactly `rate × seconds`
  samples with zero loss and no duplicates.
- `apply_calibration` returns the full set of expected columns:
  `time, Taux, temp, temp-hr, Thtr, Uref`.
- `df['Uref']` matches the commanded AO ch1 profile byte-for-byte (i.e. the
  finite-scan tiling path is correct).

### 1.2 SlowMode + AC modulation (primary focus)
- The AO `ch1` profile is the linear DC ramp **plus** a clean sinusoid:
  with a 1→3 V ramp and `ModulationParams(f=200 Hz, A=0.2 V, offset=0)`, FFT
  of the AC component recovers `f = 200.00 Hz`, `A = 0.200 V` exactly.
- Clipping to `[0, safe_voltage]` is honoured: profile range stays inside
  `[0.804, 3.196]` V — the sine is not clipped at this DC bias.
- The mock attenuates AO→AI by `0.005` on `ch1` (Umod). After
  `apply_calibration`, FFT of `temp-hr` has its peak exactly at `f_mod`.
- Lock-in amplitude on `temp-hr` is `≈ 0.00844`, theoretical value is
  `A · 0.005 · 1000 / Gain_Umod · ttpl0 = 0.2 · 0.005 · 1000 / 121 · 1.0
  ≈ 0.00826` — within ~2 %, the residual is the `sosfiltfilt` transient
  bleeding into the average.
- Lock-in phase on the steady region is `≈ 0.06 rad` (close to zero). The
  mock has no thermal RC, so a near-zero phase is expected; phase recovery
  with a known artificial lag is exercised separately by
  `test_lockin_recovers_amplitude_and_phase`.

### 1.3 IsoMode + AC modulation
- The CONTINUOUS AO buffer is `sample_rate` samples (1 s) and is repeated by
  the mock indefinitely. FFT confirms `f = 200 Hz`, `A = 0.2 V`.
- A 1.5 s ring-buffer run yields exactly `1.5 × sample_rate` AI samples.
- `df['Uref']` is tiled across the full AI length (std = 0.14, AC content
  preserved) — this is the FIX A path.
- `temp-hr_amp ≈ 0.00915` vs theoretical `≈ 0.00826`, same ~10 % envelope.

### 1.4 IsoMode DC-only
- Profile collapses to a single sample (`np.array([0.5])`); the manager
  routes through `ao_set` rather than `ao_modulated`.
- AI ring buffer still streams; `Uref` is tiled to a constant `0.5` across
  every AI sample.

### 1.5 Temperature → voltage inversion
- Production polynomial `Theater = (-2.425, 8.0393, -0.42986)` (form
  `θ₀·V + θ₁·V² + θ₂·V³`) inverts correctly:
  T = 10 °C → V ≈ 1.33; T = 150 °C → V ≈ 5.32.
- `np.maximum.accumulate` handles the historical sub-zero dip near `V ≈ 0.16`.

### 1.6 Verified by the existing test suite
- `test_fast_mode_no_point_loss` — half-buffer flip on the finite path.
- `test_slow_mode_produces_lockin_columns` — slow mode columns and lengths.
- `test_iso_mode_streams_into_dataframe` — ring buffer round-trip.
- `test_apply_calibration.py` — `Uref` tiling, `Thtr` NaN when heater idle,
  raw integer columns dropped, empty-frame edge case.
- `test_mock_uldaq.py` — race-free re-arm after `scan_stop`, shared-buffer
  semantics, scan progression.
- `test_modulation.py` — `apply_modulation`, lock-in amplitude/phase recovery
  with known phase lag, invalid input rejection.

`pytest tests/` → **33 passed in ~7 s**. `python -m pioner.back.debug` runs
all three modes end-to-end without errors.

---

## 2. What the mock cannot prove (must be done on real hardware)

The mock is an amplitude bridge AO→AI with deterministic noise. **It is not
a thermal model of the chip.** The following items pass on the mock but must
be re-validated on real hardware before MVP sign-off.

1. **`C_p` reconstruction** — The mock returns near-zero phase because there
   is no RC delay. Real heat capacity comes from the modulation phase lag.
   The lock-in algorithm itself is correct (test asserts phase recovery on a
   synthetic signal with a known 0.6 rad lag), but the physical result has
   to be cross-checked against a known sample.

2. **AO/AI start skew** — The mock does not care which scan starts first.
   On real hardware AI is armed ~100 µs before AO, which means the leading
   1–2 samples on a 1000 K/s FastHeat scan are pre-AO. The
   `hardware_trigger=True` path (see
   `BackSettings.daq_params.hardware_trigger`) closes this on real
   hardware by pre-arming both scans with `EXTTRIGGER` and firing them
   together; mock-tested but not yet validated against a physical board.
   Tracked as `todo.md` P0-5.

3. **`Ihtr` / `Rhtr` dimensions** — With the default identity calibration
   `ihtr1 = 1.0`, the formula `Rhtr = (Uhtr_mV − V_shunt·1000 + uhtr0) ·
   uhtr1 / Ihtr` produces a number in `[Ω·V/A]`, not Ω. Tests pass because
   identity is dimensionally consistent in itself, but the production
   `calibration.json` must set `ihtr1 ≈ 1/R_shunt ≈ 5.88e-4` for real Ω.
   Tracked as `todo.md` P0-3 — needs a conversation with the physicist
   before MVP claims about heater resistance.

4. **AD595 cold-junction drift** — `apply_calibration` averages `df[3]` over
   the entire scan. On slow ramps longer than ~30 s the cold-junction can
   drift by O(0.5 °C) and the average loses that. Mock returns a constant
   ~25 °C, so this is invisible in tests.

5. **Mock injects a deterministic ~196 Hz tone** — `_synthesise_sample` uses
   `math.sin(t·1234.5 + channel)·0.5e-3` as "noise". This is a coherent
   tone at ~196 Hz, visible in the FFT and in the lock-in. With the default
   `f_mod = 37.5 Hz` and the verification cases at 200 Hz it is far enough
   away to not interfere; choosing `f_mod ≈ 196 Hz` will produce a spurious
   peak. Tracked as `todo.md` P1-15.

---

## 3. Real issues left in the back-end

All of these are tracked in `todo.md`; none of them block running the three
modes against the mock or against real hardware, but they are worth knowing
before a public demo.

| Item     | Where                                             | Impact                                                                                                                                              |
|----------|---------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| P1-1     | `modes.IsoMode.run`, `iso_mode.IsoMode`           | Long iso runs cannot be aborted from the GUI/Tango; only `time.sleep(duration)` or process kill.                                                    |
| P1-4     | `modes.SlowMode._build_profiles`, `IsoMode._build_profiles` | Modulation clipping to `[0, safe_voltage]` is silent. With e.g. `DC=8.5, A=2 V, safe=9` the sine becomes a trapezoid and lock-in returns wrong amp. |
| P1-9     | `shared.modulation.lockin_demodulate`             | `sosfiltfilt` transient on each edge (~10 modulation periods). For scans <0.5 s at 37.5 Hz this is >50 % of the signal; no `valid` mask returned.   |
| P1-13    | `experiment_manager._collect_finite_ai`           | Busy poll at 1 ms → ~100 % of one core on Raspberry Pi.                                                                                             |
| P1-5     | `iso_mode.IsoMode.run(do_ai=False)`               | Legacy "Set V and hold" GUI path drops the voltage immediately; the Tango path is unaffected, but a direct Python user of the legacy class breaks. |
| P1-6     | `nanocontrol_tango.NanoControl`                   | `select_mode` + `arm` state machine is not fail-loud — a forgotten `select_mode` reuses the previous value silently.                                |
| P0-6     | `modes._validate_programs`, `_collect_finite_ai`  | Profile duration must be a whole number of seconds. Deliberate software simplification, deferred.                                                   |

---

## 4. Manual mock-DAQ usage plan

### 4.1 Quick smoke test (30 s — all three modes back-to-back)

```bash
PYTHONPATH=src .venv/bin/python -m pioner.back.debug
```

Expected output:
```
Fast mode produced 20000 samples; columns: ['time', 'Taux', 'temp', 'temp-hr', 'Thtr', 'Uref']
Slow mode: 40000 samples, lock-in columns present: ['temp-hr_amp', 'temp-hr_phase']
Iso mode: 20000 samples
```

### 4.2 Full test suite

```bash
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

33 tests, ~7 s. If any fail, do not move on.

### 4.3 Physics-aware verification (FFT, lock-in amplitude, Uref tiling)

The verification script lives at `/tmp/pioner_check/verify_pipelines.py`
(generated during this audit). Run with:

```bash
PYTHONPATH=src .venv/bin/python /tmp/pioner_check/verify_pipelines.py
```

It exercises:
- AO profile: peak voltage, length, AC FFT (frequency + amplitude).
- AI collection: sample count = `rate × seconds`.
- `Uref` tiling for finite, CONTINUOUS, and DC-iso paths.
- Lock-in amplitude vs the analytical expected value (factor of 0.5..2×).
- `temp-hr` FFT peak vs `f_mod`.
- Temperature-program → voltage inversion endpoints and midpoint.

### 4.4 Hand-driven scenarios

```python
from pioner.shared.calibration import Calibration
from pioner.shared.modulation import ModulationParams
from pioner.shared.settings import BackSettings
from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.modes import FastHeat, SlowMode, IsoMode

settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
cal = Calibration()                              # identity (V==V, T==T)
# cal.read("./settings/calibration.json")        # production polynomial

daq = DaqDeviceHandler(settings.daq_params); daq.try_connect()

# --- Slow mode with the default modulation from settings.json (37.5 Hz / 0.1 V):
slow_progs = {
    "ch0": {"time": [0, 2000], "volt": [0.1, 0.1]},
    "ch1": {"time": [0, 2000], "volt": [0,   1]},
}
m = SlowMode(daq, settings, cal, slow_progs); m.arm()
df = m.run()
df.to_hdf("data/slow_mock.h5", key="data", mode="w")
# Inspect: df['temp-hr_amp'].iloc[10000:30000].mean()
#          df['temp-hr_phase'].iloc[10000:30000].mean()

# --- Iso DC, 0.5 V for 1 s:
iso = IsoMode(daq, settings, cal, {"ch1": {"volt": 0.5}})
iso.arm(); df_iso_dc = iso.run(duration_seconds=1.0)

# --- Iso AC, with a custom modulation override:
mod = ModulationParams(frequency=200.0, amplitude=0.2, offset=0.0)
iso_ac = IsoMode(daq, settings, cal, {"ch1": {"volt": 0.5}}, modulation=mod)
iso_ac.arm(); df_iso_ac = iso_ac.run(duration_seconds=2.0)

daq.disconnect()
```

### 4.5 What to inspect on every DataFrame

| Check                                                                                  | Expectation                                                                                |
|----------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| `len(df) == sample_rate × seconds`                                                     | No samples lost.                                                                           |
| `df['Uref']`                                                                           | Equal to AO ch1 trace (FastHeat/SlowMode); tiled in iso.                                   |
| `df['temp-hr']` FFT                                                                    | Peak at `f_mod ± 1 Hz` for slow/iso AC.                                                    |
| `df['temp-hr_amp'].iloc[N//4:3*N//4].mean()`                                           | Roughly `A_mod · 0.005 · 1000 / Gain_Umod · ttpl0` on identity calibration.                |
| `df['temp-hr_phase']` mid-run                                                          | Near 0 on the mock (no thermal lag); finite and bounded on real hardware.                  |
| `df['Thtr']`                                                                           | Either physically reasonable or `NaN` (heater idle). Must **not** be ≈ −1070 °C.           |
| `df['Taux']`                                                                           | ≈ 25 °C (mock returns ~0.25 V on AI ch3, scaled ×100).                                     |

### 4.6 Tango path (optional)

The Tango server module imports cleanly without PyTango (no-op decorators) so
the mock pipeline can be exercised through its public API without a Tango
host. For the MVP demo the in-process Python path above is enough; reach for
the Tango layer only if you want to validate `set_connection / select_mode /
arm / run` wiring before real hardware.

---

## 5. Pre-real-hardware checklist (out of scope for the mock)

Before the first real-hardware run, three items in `todo.md` need attention:

1. **P0-3** — Confirm `ihtr1` semantics with the physicist; commit a
   production `calibration.json` with `ihtr1 ≈ 1/R_shunt`.
2. **P0-5** — Plan the hardware-trigger upgrade (`RETRIGGER` /
   `EXTTRIGGER`) so AO and AI start on the same DAQ pulse.
3. Awareness of the mock's coherent ~196 Hz noise tone (P1-15) and the
   `sosfiltfilt` edge transient (P1-9) when interpreting first real-hardware
   plots.

Everything else in `todo.md` is quality-of-life or code health and does not
block MVP.
