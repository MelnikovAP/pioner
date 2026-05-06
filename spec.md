# PIONER — AO / AI Pipeline Specification

This document is the technical reference for the data-acquisition pipeline of
the PIONER chip nanocalorimeter (formerly `nanocal`). It describes the path of
a single experiment from the user-supplied program to a curated DataFrame of
engineering units. It is meant to be read top-to-bottom by anyone who plans to
modify the back-end or to interface with it.

> Time conventions: profile programs are expressed in **milliseconds**.
> Internal arrays for AO/AI scans are in **seconds** (rate × seconds = samples).
> Voltages everywhere are in **volts** unless explicitly mentioned.

---

## 1. Hardware overview

* **DAQ board**: Measurement Computing USB-DAQ (`uldaq` driver). Six AI
  channels (0..5) and four AO channels (0..3) at up to 1 MS/s.
* **Chip**: thin-film calorimeter with two heaters (sample + guard), a
  thermopile (Utpl), an AD595 cold-junction sensor, and a high-resolution
  modulation channel (Umod).
* **Conditioning electronics**: instrumentation amplifiers (`Gain Utpl ≈ 11`,
  `Gain Umod ≈ 121`) and a current shunt that converts heater current into
  a voltage on AI ch0.

| AO ch | Purpose                              | AI ch | Purpose                                |
|-------|--------------------------------------|-------|----------------------------------------|
| 0     | reference / shunt-path bias (~0.1 V) | 0     | heater current shunt                   |
| 1     | **heater drive (DC + AC)**           | 1     | Umod (high-resolution thermopile)      |
| 2     | trigger / guard heater               | 3     | AD595 cold-junction (Taux)             |
| 3     | spare                                | 4     | Utpl (standard thermopile)             |
|       |                                      | 5     | Uhtr (heater voltage feedback)         |

The mapping above is **the contract** between front-end, mode classes, and
calibration. Changing it requires touching `pioner.back.modes.apply_calibration`
and the GUI's `mainWindow.fh_arm`.

---

## 2. The three experiment modes

| Mode                | Heating rate    | DC profile | AC modulation | Lock-in | Use case                                  |
|---------------------|-----------------|------------|---------------|---------|-------------------------------------------|
| `FastHeat`          | up to >1000 K/s | ramps      | no            | no      | ballistic transitions, glass / melting    |
| `SlowMode`          | 0.01–10 K/s     | ramps      | yes           | yes     | small-signal AC calorimetry on ramps      |
| `IsoMode`           | T = const       | constant   | optional      | yes if AC| AC heat capacity at fixed T              |

Why modulation in slow / iso? On microgram samples the DC signal is buried in
1/f noise of the analog front-end. Adding a small `A·sin(2πft)` (typically
`f = 37.5 Hz`, `A = 0.1 V`) on the heater drive produces an AC temperature
response whose amplitude/phase encode the heat capacity. We recover them in
software via single-frequency lock-in (`scipy.signal.sosfiltfilt` Butterworth
LP, zero phase lag).

---

## 3. The full AO / AI pipeline

```
┌───────────────────────────────────────────────────────────────────┐
│ 1. USER → PROGRAM                                                 │
│   {"ch1": {"time": [0, 500, 1000], "temp": [10, 100, 10]}, ...}   │
│   - keys: "chN" with N ∈ [ao_low, ao_high]                        │
│   - exactly one of "temp" (°C) or "volt" (V)                      │
│   - common duration must be a whole number of seconds (TODO)      │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 2. modes._validate_programs()                                     │
│   - rejects unknown channel keys                                  │
│   - rejects non-monotonic time arrays                             │
│   - enforces program duration % 1 s == 0                          │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 3. modes._program_to_voltage()                                    │
│   - linear interpolation onto the AO sample grid                  │
│     (samples_per_channel = sample_rate · seconds)                 │
│   - if program is in °C: temperature_to_voltage(...)              │
│       • clamps requested T into [min_temp, max_temp]              │
│       • 90 000-point V grid → cumulative-max(T(V)) → searchsorted │
│       • tolerates the historical sub-zero dip near V≈0.16         │
│   - SlowMode/IsoMode add AC modulation on the modulation_channel  │
│       (default ch1) and clip back to [0, safe_voltage]            │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 4. ScanDataGenerator.flatten()                                    │
│   AO buffer layout (interleaved):                                 │
│      [ch0_t0, ch1_t0, ..., chN_t0, ch0_t1, ch1_t1, ...]           │
│   - missing channels in [ao_low, ao_high] are zero-filled         │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 5. ExperimentManager  (.finite_scan / .ao_modulated / .ao_set)    │
│   AI buffer = sample_rate samples per channel  (= 1 s of data)    │
│   ─ a ─ AI_scan starts FIRST (ScanOption.CONTINUOUS)              │
│   ─ b ─ AO_scan starts SECOND (ScanOption.BLOCKIO for finite,     │
│         CONTINUOUS for slow/iso modulation)                       │
│   ─ c ─ poll ai.get_scan_status().current_index every 1 ms        │
│   ─ d ─ on each half-buffer flip, copy that half into a numpy     │
│         chunk and append to ``chunks: list[ndarray]``             │
│   ─ e ─ stop when ``collected ≥ seconds × sample_rate``           │
│   ─ f ─ AO scan_stop, AI scan_stop, return DataFrame              │
│                                                                   │
│   IsoMode also exposes:                                           │
│     start_ring_buffer()  → spawns a daemon thread that does the   │
│                            same half-buffer flips into a deque    │
│                            of bounded length (default 10 s)       │
│     stop_ring_buffer()   → joins thread                           │
│     snapshot_ring_buffer() → np.concatenate(deque)                │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 6. modes.apply_calibration()  raw → engineering units             │
│                                                                   │
│   time      = arange(N) * 1000 / sample_rate                  [ms]│
│                                                                   │
│   Taux      = AD595 correct(100 · mean(U_AI3))                [°C]│
│              # TODO(physical): replace mean() by per-sample.      │
│                                                                   │
│   Utpl_mV  = U_AI4 · 1000 / Gain_Utpl                  [mV]       │
│   temp     = Ttpl_poly(Utpl_mV + utpl0) + Taux        [°C]        │
│                                                                   │
│   Umod_mV  = U_AI1 · 1000 / Gain_Umod                  [mV]       │
│   temp-hr  = Ttpl_poly(Umod_mV + utpl0)               [°C]        │
│                                                                   │
│   Uhtr_mV  = U_AI5 · 1000                              [mV]       │
│   Ihtr     = ihtr0 + ihtr1 · U_AI0                     [A]        │
│   Rhtr     = (Uhtr_mV − U_AI0·1000 + uhtr0) · uhtr1 / Ihtr  [Ω·…] │
│   Thtr     = Thtr_poly(Rhtr + thtrcorr)               [°C]        │
│                                                                   │
│   Uref     = ch1 voltage profile (debug context)      [V]         │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 7. SlowMode / IsoMode lock-in (scipy.signal.sosfiltfilt)          │
│    in_phase(t)   = signal · sin(ωt)                               │
│    quadrature(t) = signal · cos(ωt)                               │
│    LP both with 4th-order Butterworth, Wn = (f / 5) / (fs/2)      │
│    amp(t)        = 2 · sqrt(in_phase_lp² + quadrature_lp²)        │
│    phase(t)      = −arctan2(quadrature_lp, in_phase_lp)           │
│        # positive phase = signal lags the AO reference            │
│    Output columns: temp-hr_amp, temp-hr_phase                     │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 8. Optional persistence (FastHeat / SlowMode legacy facades)      │
│    HDF5 file ``data/exp_data.h5`` with:                           │
│      data/{time, Taux, Thtr, Uref, temp, temp-hr, [..._amp,phase]}│
│      voltage_profiles/{ch0..chN}                                  │
│      temp_volt_programs/{chN}/{time, temp|volt}                   │
│      calibration   (json string blob)                             │
│      settings      (json string blob)                             │
└───────────────────────────────────────────────────────────────────┘
```

### Half-buffer reading (no point loss)

The AI buffer is exactly `sample_rate` samples per channel = 1 s of data. We
read it via the half-buffer flip protocol that real DMA-based DAQ APIs use:

1. AI buffer is laid out flat: `n_chans × sample_rate` floats.
2. The driver fills it cyclically and exposes `current_index` (flat-buffer
   units) via `get_scan_status()`.
3. The poller (1 ms cadence) tracks `last_index`. When `current_index`
   crosses the half-buffer boundary upwards, the **lower half** is now stable
   and we copy it. When `current_index` wraps back (idx < last_index, last
   was in the upper half) the **upper half** is stable and we copy it.
4. Each chunk is a `(half_per_channel, n_chans)` numpy view, copied into the
   `chunks` list. Total `O(seconds × sample_rate × n_chans × 8)` bytes,
   trimmed at the end to exactly `seconds × sample_rate` samples.

This is symmetric in `_collect_finite_ai` (paced finite scan) and `_ring_loop`
(continuous iso mode).

### AO/AI synchronisation

Both scans share the same DAQ board's onboard pacer, so the relative drift
between them is bounded by clock jitter (negligible on the timescale of any
realistic scan). We do, however, start AI a few hundred microseconds before
AO so we never miss the first AO sample. This means the AI frame contains
those leading "pre-AO" samples; for fast mode (>1000 K/s) the leading edge
is therefore offset by 1–2 samples. See the global TODOs below for the
hardware-trigger fix.

---

## 4. Calibration

The `Calibration` dataclass holds two groups of parameters:

* **Chip-specific** (per sensor): `Theater`, `Ttpl`, `Thtr`, `Thtrd`, `Uhtr`,
  `Ihtr`, `Amplitude correction`, `R heater`, `R guard`, `Heater safe voltage`.
  These are produced by the calibration procedure and live next to each chip.
* **Hardware-side** (electronics): `Gain Utpl`, `Gain Umod`,
  `AD595 low correction`. These are properties of the *signal-conditioning
  board*, not of the chip; they live in the new `Hardware` block of the
  calibration JSON. Defaults are `11.0`, `121.0`, and the historical
  AD595 < −12 °C polynomial.

The polynomial inversion (`temperature_to_voltage`) tolerates the small
sub-zero dip the historical 39392 polynomial has near `V ≈ 0.16 V`: we
monotonise the temperature grid via `np.maximum.accumulate` before
`searchsorted`. Catastrophic non-monotonicity (`T(V_max) ≤ T(0)`) is still
rejected.

---

## 5. Mock backend

`pioner.back.mock_uldaq` ships a pure-Python simulator that is auto-selected
when the real `uldaq` cannot be imported (libuldaq missing on macOS, etc.).
Key contract guarantees:

* `create_float_buffer(...)` returns a Python list (real uldaq returns a
  ctypes float array). Both shapes accept slice assignment.
* `a_in_scan` does not copy the buffer. The mock spawns a daemon thread that
  mutates the very list passed in so callers can poll progress.
* `current_index` and `current_scan_count` advance with wall-clock time.
* When an AO scan is active, AI samples are derived from `voltage_at(ch, t)`
  with a deterministic ~0.5 mV noise term. **This is not a thermal model of
  the chip** — only enough to exercise the post-processing pipeline.
* `scan_stop` joins the worker before returning, so re-arming a new scan is
  race-free.

`debug.py` is the smoke-test entry point:

```bash
PYTHONPATH=src python -m pioner.back.debug
```

---

## 6. Tango layer

`pioner.back.nanocontrol_tango.NanoControl` is a single-device server.

| Command                  | Args            | Description                                       |
|--------------------------|-----------------|---------------------------------------------------|
| `set_connection`         | -               | discovery + connect to USB-DAQ                    |
| `disconnect`             | -               | release the DAQ                                   |
| `apply_default_calibration` | -            | reload `default_calibration.json`                 |
| `apply_calibration`      | -               | reload `calibration.json`                         |
| `load_calibration`       | str (json blob) | overwrite `calibration.json` from outside         |
| `set_sample_scan_rate`   | int             | change AI/AO rate                                 |
| `select_mode`            | str (`fast/slow/iso`) | choose the next mode to arm                |
| `arm`                    | str (json programs)   | build voltage profiles, ready to run        |
| `run`                    | -               | execute the armed mode                            |
| `arm_fast_heat` / `run_fast_heat` | (legacy) | shortcuts that pre-select fast            |
| `arm_iso_mode` / `run_iso_mode`   | (legacy) | shortcuts that pre-select iso             |

PyTango is *optional*: importing `nanocontrol_tango` without PyTango installed
falls through to a no-op decorator stack so unit tests can still import the
module.

---

## 7. Front-end (Qt5 / silx)

`pioner.front.mainWindow` is the live experiment GUI. It currently exposes:

* connection / calibration / data-path management,
* a fast-mode profile editor (time × temperature/voltage table) → `arm_fast_heat`,
* a "Set / Off" pair that pushes a constant voltage to the heater
  channel `ch1` (after recent fix; previously inconsistent — see TODOs),
* download of `raw_data.h5` / `exp_data.h5` from the device's HTTP endpoint,
* result plotting via silx.

**Slow mode is NOT yet exposed in the GUI**: the user can only run fast or
iso. Wiring slow mode requires a `select_mode("slow")` button and the
existing profile editor (see global TODOs). The Tango layer is ready.

---

## 8. Outstanding work / global TODOs

The following are tracked as `TODO(...)` comments next to the relevant code.
They are listed here for project-management visibility. None block the
3-mode pipeline from working end-to-end on mock and on real hardware.

### Global / architectural

1. **Sub-second program durations** — lift the
   `program_duration % 1 s == 0` constraint by sizing the AI buffer to
   `ceil(seconds) * sample_rate` and trimming the trailing tail. Touched in
   `experiment_manager._collect_finite_ai` and `modes._validate_programs`.
2. **Hardware trigger** — start AO and AI on the same DAQ pulse via
   `ScanOption.RETRIGGER` (or `EXTTRIGGER` if a digital line is wired). This
   removes the ~hundreds-of-µs leading skew that currently means the first
   1–2 samples of AI are pre-AO.
3. **External interrupt for IsoMode** — replace the plain
   `time.sleep(duration_seconds)` in `IsoMode.run` with a
   `threading.Event` exposed at the Tango / GUI level so long-running iso
   experiments can be aborted mid-flight.
4. **Slow mode in the GUI** — add a mode dropdown and reuse the existing
   profile editor. Backend (`select_mode("slow")`, `arm`, `run`) is already
   plumbed.

### Physical fidelity

5. **AD595 Taux is averaged over the whole scan** — replace `df[3].mean()`
   in `apply_calibration` by either a per-sample correction or a
   low-pass-filtered trace. Drift over long slow ramps (>30 s) is
   O(0.5 °C) on lab-temperature changes.
6. **Temperature-to-voltage monotonicity** — when committing a new chip
   `Theater` polynomial, verify `dT/dV > 0` everywhere on
   `[0, safe_voltage]`. The current production polynomial
   `(-2.425, 8.04, -0.43)` has a tiny dip we tolerate via cumulative-max,
   but coefficient drift can widen it.
7. **AC bandwidth vs ramp rate (slow mode)** — the lock-in default
   `bandwidth = f / 5 = 7.5 Hz` corresponds to a settling time
   `~0.13 s`. For ramp rates above ~5 K/s the bandwidth starts smearing the
   `C_p(T)` curve. Make `bandwidth` an explicit `ModulationParams` field.
8. **Mock realism** — the mock copies AO voltage to AI ch5, scales it to
   put a small thermopile signal on ch1/ch4, and exposes ~25 °C on ch3. It
   does not simulate the chip's RC thermal response, so testing C_p
   reconstruction algorithms against the mock is not meaningful. Add a
   minimal first-order RC model to `mock_uldaq.MockAiDevice` if needed.
9. **Half-buffer flip in iso ring-buffer relies on continuous AI scan** —
   if the user stops/restarts AO during an iso run we may land in a state
   where the buffer is fresh and `current_index` has not wrapped yet. The
   ring loop handles "no chunk yet" gracefully (returns empty snapshot)
   but it's worth documenting.

### Code-quality

10. **Wildcard import `from pioner.shared.constants import *`** in
    `settings.py` and `front/mainWindow.py` makes refactors brittle.
    Replace by explicit imports.
11. **`mainWindow.fh_arm` profile cleanup** —
    `correctedProfile = uncorrectedProfile[:, :np.argmax(uncorrectedProfile[0])+1]`
    silently truncates the program at the first non-monotonic time. Should
    raise instead.
12. **Async `_fh_download_*` methods** in `mainWindow` block the UI thread
    on slow networks. Run in a `QThread` if it becomes painful.

---

## 9. Test matrix

| Test file              | Coverage                                             |
|------------------------|------------------------------------------------------|
| `test_calibration.py`  | identity, clamping, vectorised round-trip, error paths, production polynomial inverts |
| `test_modulation.py`   | `apply_modulation`, lock-in amplitude/phase recovery, edge cases |
| `test_mock_uldaq.py`   | lifecycle, shared buffer, scan progression, race-free re-arm |
| `test_modes_e2e.py`    | fast / slow / iso end-to-end on mock; temp-program path; validation errors |

```bash
PYTHONPATH=src pytest tests/             # 26 tests, ~6 s
PYTHONPATH=src python -m pioner.back.debug   # smoke test all 3 modes
```

The mock-specific tests are skipped when a real `uldaq` driver is detected
(set `UL_USE_MOCK=1` is *not* needed; we just check `DAQ_AVAILABLE`).
