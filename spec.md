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
  channels (0..5) and four AO channels (0..3) at up to 1 MS/s. Default
  scan rate `fs = 20 kHz` (see `settings/default_settings.json`,
  `Experiment settings.Scan.Sample rate`). The half-buffer flip protocol
  (§3) requires `fs` to be **even**; non-even values are rejected at
  `_collect_finite_ai` and `start_ring_buffer`.
* **Chip**: thin-film calorimeter with two heaters (sample + guard), a
  thermopile (Utpl), an AD595 cold-junction sensor, and a high-resolution
  modulation channel (Umod). Heater nominal R ≈ 1700 Ω; current shunt also
  ≈ 1700 Ω in series.
* **Conditioning electronics**: instrumentation amplifiers (`Gain Utpl ≈ 11`,
  `Gain Umod ≈ 121`) and a current shunt that converts heater current into
  a voltage on AI ch0.
* **Analog range**: the JSON setting `RangeId = 5` selects `BIPxxVOLTS = ±10 V`
  (see `mock_uldaq.Range`). `AoDeviceHandler.set_voltage` and `.scan` reject
  any value or buffer peak outside the range with a `ValueError`
  (`_RANGE_MAX_VOLTAGE` table in `back/ao_device.py`). This is a hardware-
  layer guard; the chip-specific `safe_voltage` (default 9 V) is enforced
  upstream by `modes._program_to_voltage`.

Channel layout (named in `pioner.shared.channels`):

| AO ch | Const          | Purpose                                  | AI ch | Const             | Purpose                                |
|-------|----------------|------------------------------------------|-------|-------------------|----------------------------------------|
| 0     | `SHUNT_BIAS_AO`| shunt-path bias (~0.1 V)                 | 0     | `HEATER_CURRENT_AI`| V across the heater current shunt     |
| 1     | `HEATER_AO`    | **heater drive (DC + AC)**               | 1     | `UMOD_AI`         | Umod (high-resolution thermopile, gain 121) |
| 2     | `GUARD_AO`     | guard heater / trigger                   | 3     | `AD595_AI`        | AD595 cold-junction (Taux)             |
| 3     | `SPARE_AO`     | spare                                    | 4     | `UTPL_AI`         | Utpl (standard thermopile, gain 11)    |
|       |                |                                          | 5     | `UHTR_AI`         | heater-side drive feedback (the `Rhtr` formula in §6/§10 needs `V_AI5 − V_AI0 = I·R_heater`, so this is the total drive to GND, not the V across the heater alone) |

The mapping above is **the contract** between front-end, mode classes, and
calibration. Changing it requires touching `pioner.back.modes.apply_calibration`,
`pioner.shared.channels`, and the GUI's `mainWindow.fh_arm`.

Wire-format: user programs and HDF5/Tango blobs use literal `"chN"` strings
(`pioner.shared.channels.channel_key`); internal Python references go through
the named constants above.

---

## 2. The three experiment modes

| Mode       | Heating rate     | DC profile | AC modulation | Demodulation                | AO ScanOption | AI ScanOption | Use case                                  |
|------------|------------------|------------|---------------|-----------------------------|---------------|---------------|-------------------------------------------|
| `FastHeat` | up to >1000 K/s  | ramps      | no            | none                        | `BLOCKIO`     | `CONTINUOUS`  | ballistic transitions, glass / melting    |
| `SlowMode` | 0.01–10 K/s      | ramps      | yes (lockin)  | per-sample time-domain      | `BLOCKIO`     | `CONTINUOUS`  | small-signal AC calorimetry on ramps      |
| `IsoMode`  | `T = const`      | constant   | optional      | per-sample lock-in **+ FFT** harmonics 1f/2f/3f when AC on | DC: `a_out`; AC: `CONTINUOUS` | `CONTINUOUS` (ring buffer) | AC heat capacity at fixed T |

Why modulation in slow / iso? On microgram samples the DC signal is buried in
1/f noise of the analog front-end. Adding a small `A·sin(2πft)` on the heater
drive produces an AC temperature response whose amplitude/phase encode the
heat capacity. We recover them in software via single-frequency lock-in
(`scipy.signal.sosfiltfilt` Butterworth LP, zero phase lag) and, in iso, also
via integer-cycle FFT for harmonic-resolved scalars.

**Modulation defaults** (in `settings/default_settings.json`,
`Experiment settings.Modulation`): `Frequency = 37.5 Hz`, `Amplitude = 0.1 V`,
`Offset = 0.0 V`. The 37.5 Hz default is **not seamless** in the 1-second
AO buffer at `fs = 20 kHz` (37.5 cycles → π-rad jump per CONTINUOUS wrap);
`IsoMode.arm` logs a `WARNING` quantifying the leakage. Pick `f_mod` from
`{1, 2, 4, 5, 8, 10, 16, 20, 25, 40, 50, ...}` Hz to make the buffer
seamless. See §3.7c.

**Modulation gating** (`ModulationParams.enabled` and `lockin_capable`):

* `enabled = (amplitude > 0) or (offset != 0)` — controls whether
  `apply_modulation` adds anything to the base profile and whether
  `IsoMode._build_profiles` takes the CONTINUOUS or DC-only branch.
* `lockin_capable = (amplitude > 0) and (frequency > 0)` — gates the
  lock-in / FFT post-processing in slow/iso `run()`.

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
│ 3. modes._program_to_voltage()    (called by every mode's         │
│                                    _build_profiles, including the │
│                                    iso DC-only branch)            │
│   - linear interpolation onto the AO sample grid                  │
│     (samples_per_channel = sample_rate · seconds; iso AC: 1 s,    │
│      iso DC: 1 sample)                                            │
│   - if program is in °C: temperature_to_voltage(...)              │
│       • clamps requested T into [min_temp=0, max_temp]            │
│       • 90 000-point V grid → cumulative-max(T(V)) → searchsorted │
│       • tolerates the historical sub-zero dip near V≈0.16         │
│   - if program is raw `volt`: NO auto-clip (user may want         │
│       negative volts on the guard channel) but logs a WARNING     │
│       when |peak| > safe_voltage.                                 │
│   - SlowMode + IsoMode AC: apply_modulation adds                  │
│       offset + A·sin(2π·f·t) to the modulation_channel (default   │
│       HEATER_AO/ch1), then np.clip into [0, safe_voltage].        │
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
│ 5. ExperimentManager                                              │
│   AI buffer = sample_rate samples per channel = 1 s of data;      │
│   sample_rate must be EVEN (half-buffer reshape).                 │
│                                                                   │
│   FastHeat / SlowMode → finite_scan(profiles, ai_chans, seconds): │
│     a) AI armed first (CONTINUOUS), AO armed second (BLOCKIO);    │
│        with hardware_trigger=True both pre-arm with EXTTRIGGER    │
│        and fire_software_trigger() releases them on a shared t=0. │
│     b) _collect_finite_ai polls current_index at 1 ms cadence     │
│        and copies each half-buffer into ``chunks: list[ndarray]`` │
│        on flip; trims to seconds·sample_rate at the end.          │
│     c) AO scan_stop, AI scan_stop, return ScanResult(df, rates).  │
│                                                                   │
│   IsoMode AC → ao_modulated(profiles) + start_ring_buffer:        │
│     a) ao_modulated arms AO with CONTINUOUS (+ EXTTRIGGER if      │
│        hardware_trigger). The AO buffer holds exactly 1 s of      │
│        samples and replays indefinitely.                          │
│     b) start_ring_buffer arms AI with CONTINUOUS (+ EXTTRIGGER if │
│        AO was triggered) and fires the trigger; spawns a daemon   │
│        ``AiRingBuffer`` thread that flips half-buffers into a     │
│        bounded deque (default ring_buffer_seconds = 10 s, so up   │
│        to 20 half-second chunks).                                 │
│     c) snapshot_ring_buffer() returns np.concatenate(deque).      │
│                                                                   │
│   IsoMode DC → ao_set(channel, V) + start_ring_buffer:            │
│     a) ao_set is an immediate a_out (NOT a scan); AI is armed     │
│        with plain CONTINUOUS (no trigger needed: nothing on AO    │
│        to synchronise with).                                      │
│                                                                   │
│   stop() teardown ordering: AO first (drop heater), AI second.    │
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
│   Ihtr     = ihtr0 + ihtr1 · U_AI0                     [A]        │
│   Rhtr     = (U_AI5 − U_AI0 + uhtr0) · uhtr1 / Ihtr   [Ω]         │
│            (V/A; production ihtr1 = 1/R_shunt → ih in amperes)    │
│   Thtr     = Thtr_poly(Rhtr + thtrcorr)               [°C]        │
│            (NaN where |Ihtr| < 1 nA — heater idle)                │
│                                                                   │
│   Uref     = AO ch1 voltage profile (heater command)  [V]         │
│            (tiled to AI length for iso/CONTINUOUS AO)             │
└───────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│ 7. SlowMode / IsoMode demodulation                                │
│                                                                   │
│ 7a. Time-domain lock-in (scipy.signal.sosfiltfilt) -- both modes  │
│    in_phase(t)   = signal · sin(ωt)                               │
│    quadrature(t) = signal · cos(ωt)                               │
│    LP both with 4th-order Butterworth, Wn = (f / 5) / (fs/2)      │
│    amp(t)        = 2 · sqrt(in_phase_lp² + quadrature_lp²)        │
│    phase(t)      = −arctan2(quadrature_lp, in_phase_lp)           │
│        # positive phase = signal lags the AO reference            │
│    Output columns: temp-hr_amp, temp-hr_phase                     │
│                                                                   │
│ 7b. FFT demodulation (IsoMode only)  -- shared.modulation.        │
│     fft_demodulate                                                │
│    Iso is stationary, so a single global (A, phi) is the natural  │
│    physical observable. We pick the largest sub-window of length  │
│    N <= len(signal) such that N · f / fs is an integer (Fraction- │
│    based; for f=37.5 Hz at fs=20 kHz this picks N=19200, i.e.     │
│    36 cycles). Inside that window the rectangular FFT has zero    │
│    spectral leakage at the harmonic bins and we read              │
│        A_h   = 2 · |X[h·k_f]| / N                                 │
│        phi_h = -π/2 - arg(X[h·k_f]) + h·ω·t_start                 │
│    where t_start = (len-N)/fs (we use the trailing slice to skip  │
│    any thermal startup transient; the +h·ω·t_start term shifts    │
│    the phase reference back to sample 0 of the original input,    │
│    so FFT and time-domain lock-in agree on stationary inputs).    │
│    Harmonics 1f / 2f / 3f are extracted at no extra cost; 2f and  │
│    3f are useful in AC calorimetry as a check on heater linear-   │
│    ity. Output: df.attrs['temp-hr_fft'] = {h: {amplitude, phase}} │
│    plus df.attrs['temp-hr_fft_leakage'] (fraction of AC power not │
│    at the requested harmonics).                                   │
│                                                                   │
│ 7c. AO modulation buffer integrity check (IsoMode only) --        │
│     shared.modulation.check_ao_period_integrity                   │
│    IsoMode replays the AO buffer CONTINUOUS, so unless the buffer │
│    covers an integer number of AC cycles every wrap injects a     │
│    phase jump of 2π·(cycles - round(cycles)) rad. The check       │
│    quantifies cycles_drift, phase_jump_rad, and the resulting     │
│    spectral leakage; logs a WARNING at IsoMode.arm() when         │
│    seamless=False. Fix in production: choose f_mod so that        │
│    n·f_mod/fs is integer (e.g. at fs=20 kHz, pick f from          │
│    {1, 2, 4, 5, 8, 10, 16, 20, 25, 40, 50, ...} Hz; the historic  │
│    37.5 Hz default is *not* in this set and produces a π-rad      │
│    jump per wrap).                                                │
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

`half_buf_len` is computed as `half_per_channel × n_chans`, **not**
`len(buf) // 2` — so the channel-alignment of the flat buffer never depends
on whether `samples_per_channel` and `n_chans` happen to share a common
factor.

`samples_per_channel = sample_rate` must be **even**: the upper-half slice
has `samples_per_channel - half_per_channel` rows, which equals
`half_per_channel` only when even. Both `_collect_finite_ai` and
`start_ring_buffer` raise `ValueError` on odd rates; the Tango command
`set_sample_scan_rate` rejects them up-front (`int` in
`[2, MAX_SCAN_SAMPLE_RATE = 1_000_000]`, even).

This is symmetric in `_collect_finite_ai` (paced finite scan) and `_ring_loop`
(continuous iso mode).

### AO/AI synchronisation

Both scans share the same DAQ board's onboard pacer, so the relative drift
between them is bounded by clock jitter (negligible on the timescale of any
realistic scan). Per-mode arming order is documented in §3 step 5 above; the
trigger contract is the same for all CONTINUOUS-AO modes (slow/iso AC) and
for finite scans (fast).

Two start modes are supported:

* **Sequential start (default, ``BackSettings.daq_params.hardware_trigger
  = False``).** Each mode arms its scans in the order described in §3
  step 5. The two ``scan()`` calls are separated by ~100 µs of Python and
  one USB round-trip; AI typically contains a few "pre-AO" samples on
  the leading edge. For fast mode (>1000 K/s) the leading edge is
  therefore offset by 1–2 samples.
* **Hardware trigger (``hardware_trigger = True``).** All paced scans
  pre-arm with ``ScanOption.EXTTRIGGER`` and stay idle until
  ``DaqDeviceHandler.fire_software_trigger()`` pulses the trigger line.
  AO and AI then start on the same DAQ clock edge — no skew. This
  applies to:
   - ``finite_scan`` (FastHeat / SlowMode): trigger fired after AI **and**
     AO are armed.
   - ``ao_modulated`` + ``start_ring_buffer`` (IsoMode AC): AI inherits
     the trigger flag from the active AO scan; trigger fired by
     ``start_ring_buffer`` once AI is armed.
   - DC iso (``ao_set`` + ``start_ring_buffer``): AO is not a scan, so AI
     is armed plain CONTINUOUS regardless of ``hardware_trigger``.
  The mock implements EXTTRIGGER as a shared ``threading.Event`` plus a
  single ``time.monotonic()`` reference for both workers; this path is
  exercised by ``test_fast_mode_with_hardware_trigger_runs_clean`` and
  ``test_iso_ac_with_hardware_trigger_runs_clean``. Real-hardware
  loopback validation (1 kHz square wave on AO ch1 → AI ch1, leading
  edge ≤ 1 sample) is still pending — see ``todo.md`` P0-5.

---

## 4. Calibration

The `Calibration` dataclass (`pioner.shared.calibration`) holds two groups of
parameters:

* **Chip-specific** (per sensor): `Theater`, `Ttpl`, `Thtr`, `Thtrd`, `Uhtr`,
  `Ihtr`, `Amplitude correction`, `R heater`, `R guard`, `Heater safe voltage`.
  Produced by the calibration procedure, live next to each chip.
* **Hardware-side** (electronics): `Gain Utpl`, `Gain Umod`,
  `AD595 low correction`. These are properties of the *signal-conditioning
  board*, not of the chip; they live in the `Hardware` block of the
  calibration JSON (defaults `11.0`, `121.0`, and the historical
  AD595 < −12 °C polynomial `[2.6843, 1.2709, 0.0042867, 3.4944e-05]`).

### Coefficient units (load-bearing)

Identifiers and unit conventions used by `apply_calibration`:

| Coefficient   | Symbol in code   | Unit / convention                                       |
|---------------|------------------|---------------------------------------------------------|
| `Utpl.0`      | `utpl0`          | mV (added to the `gain`-corrected thermopile voltage)   |
| `Ttpl.{0,1}`  | `ttpl0, ttpl1`   | °C/mV, °C/mV² (polynomial in `Utpl + utpl0`)            |
| `Uhtr.{0,1}`  | `uhtr0, uhtr1`   | V, dimensionless (`(V_AO − V_shunt + uhtr0) · uhtr1`)   |
| `Ihtr.{0,1}`  | `ihtr0, ihtr1`   | A, **siemens** (`ih = ihtr0 + ihtr1·V_shunt` → amperes); production sets `ihtr1 ≈ 1/R_shunt ≈ 5.88e-4 S` |
| `Thtr.{0,1,2,corr}` | `thtr0..2, thtrcorr` | polynomial in **ohms** (R + thtrcorr); production `(-1069.7, 0.78336, -8.67e-5)` gives `T(R=1700 Ω) ≈ 11.5 °C` |
| `Theater.{0,1,2}`  | `theater0..2`   | °C/V, °C/V², °C/V³ (cubic in `V_heater_drive`); production `(-2.425, 8.04, -0.43)` |
| `R heater`    | `rhtr`           | Ω (metadata, not used in formulas — informational)      |
| `Heater safe voltage` | `safe_voltage` | V; clamps temp programs and AC modulation peak       |

Default-constructed `Calibration` is the **identity** (`utpl0=0`,
`ttpl0=ihtr1=uhtr1=theater0=...=1`), useful as a unit-test fallback. With
identity, derived quantities are dimensionally meaningless — never use them
to back out physical numbers. See `tests/test_apply_calibration.py
::test_rhtr_units_are_ohms_with_production_calibration` for the regression
that pins the V-domain numerator (`R = (V_AO - V_shunt + uhtr0)·uhtr1 / I`)
in ohms.

### Temperature → voltage inversion

`temperature_to_voltage` (in `pioner.shared.utils`) inverts the cubic
`Theater` polynomial numerically: 90 000-point V grid over
`[0, safe_voltage]`, `np.maximum.accumulate(T(V))` to monotonise, then
`np.searchsorted(temp_mono, temp_clipped)`. Catastrophic non-monotonicity
(`T(V_max) ≤ T(0)`) is rejected with `ValueError`; the small sub-zero dip
the historical 39392 polynomial has near `V ≈ 0.16 V` is tolerated by the
cumulative-max. Output is rounded to 4 decimals — slightly tighter than the
16-bit DAC LSB (~0.305 mV), so the rounding does not matter on real
hardware (see `todo.md` P2-19).

---

## 5. Mock backend

`pioner.back.mock_uldaq` ships a pure-Python simulator that is auto-selected
when the real `uldaq` cannot be imported (libuldaq missing on macOS, etc.).
Selection is silent (no env-var, no flag) — see `DAQ_AVAILABLE` in the same
module. Key contract guarantees:

* `create_float_buffer(...)` returns a Python list (real uldaq returns a
  ctypes float array). Both shapes accept slice assignment.
* `a_in_scan` does not copy the buffer. The mock spawns a daemon thread that
  mutates the very list passed in so callers can poll progress.
* `current_index` and `current_scan_count` advance with wall-clock time.
* When an AO scan is active, AI samples are derived from `voltage_at(ch, t)`
  + deterministic ~0.5 mV noise term. **This is not a thermal model of
  the chip** — only enough to exercise the post-processing pipeline. The
  noise term is `math.sin(t·1234.5 + channel)·0.5e-3`, a coherent ~196 Hz
  tone visible in any FFT. Avoid choosing `f_mod` near 196 Hz when running
  iso/slow tests on the mock (todo.md P1-15).
* `scan_stop` joins the worker before returning, so re-arming a new scan is
  race-free.
* `EXTTRIGGER` is implemented as `_SharedScanState.trigger_event` +
  `trigger_t0`: AO and AI workers block on the same event and read the same
  monotonic time at fire. This is the authoritative simulation of the
  hardware-trigger path.
* The mock does **not** enforce the analog range — the
  `_RANGE_MAX_VOLTAGE` guard in `AoDeviceHandler` does, and matches the
  way real uldaq saturates / errors. Tests assume that guard catches
  out-of-range values in both `set_voltage` and `scan` paths.

`debug.py` is the smoke-test entry point:

```bash
PYTHONPATH=src .venv/bin/python -m pioner.back.debug
```

---

## 6. Tango layer

`pioner.back.nanocontrol_tango.NanoControl` is a single-device server.

Commands:

| Command                        | Args                     | Description                                                |
|--------------------------------|--------------------------|------------------------------------------------------------|
| `set_connection`               | —                        | discovery + connect to USB-DAQ                             |
| `disconnect`                   | —                        | release the DAQ                                            |
| `apply_default_calibration`    | —                        | reload `default_calibration.json`                          |
| `apply_calibration`            | —                        | reload `calibration.json`                                  |
| `load_calibration`             | `str` (json blob)        | overwrite `calibration.json` from outside                  |
| `set_sample_scan_rate`         | `int`                    | change AI/AO rate; rejects non-even or out-of-range values |
| `reset_sample_scan_rate`       | —                        | re-parse rate from `BackSettings`                          |
| `select_mode`                  | `str` (`fast/slow/iso`)  | choose the next mode to arm                                |
| `arm`                          | `str` (json programs)    | build voltage profiles, ready to run                       |
| `run`                          | —                        | execute the armed mode (blocks for finite scans, returns   |
|                                |                          | when iso reaches `duration_seconds` or `stop_run` fires)   |
| `stop_run`                     | —                        | request abort of the running mode (iso `stop()`)           |
| `arm_fast_heat`/`run_fast_heat`| (legacy)                 | shortcuts that pre-select fast                             |
| `arm_iso_mode`/`run_iso_mode`  | (legacy)                 | shortcuts that pre-select iso                              |

Pipes (Tango read-only attributes):

| Pipe                           | Returns                                                                |
|--------------------------------|------------------------------------------------------------------------|
| `get_info`                     | static dev/contact/model metadata                                      |
| `get_current_calibration`      | `Calibration.get_str()` JSON                                           |
| `get_sample_rate`              | `{"sr": ai_params.sample_rate}`                                        |

PyTango is *optional*: importing `nanocontrol_tango` without PyTango installed
falls through to a no-op decorator stack so unit tests can still import the
module.

---

## 7. Front-end (Qt5 / silx)

`pioner.front.mainWindow` is the live experiment GUI. It currently exposes:

* connection / calibration / data-path management,
* a fast-mode profile editor (time × temperature/voltage table) → `arm_fast_heat`,
* a "Set / Off" pair that pushes a constant voltage to the heater
  channel `ch1` (iso DC),
* download of `raw_data.h5` / `exp_data.h5` from the device's HTTP endpoint,
* result plotting via silx.

**Slow mode is NOT yet exposed in the GUI**: the user can only run fast or
iso. Wiring slow mode requires a `select_mode("slow")` button and the
existing profile editor (see §8 item 3). The Tango layer is ready.

---

## 8. Outstanding work / global TODOs

The authoritative, prioritised list is in `todo.md`. The items below summarise
what is still open after the 2026-05-09 audit (all listed bugs in todo.md
sections P0/P1 that are not yet closed). None block the 3-mode pipeline from
working end-to-end on mock or on real hardware.

### Global / architectural

1. **Sub-second program durations** — lift the
   `program_duration % 1 s == 0` constraint by sizing the AI buffer to
   `ceil(seconds) * sample_rate` and trimming the trailing tail. Touched in
   `experiment_manager._collect_finite_ai` and `modes._validate_programs`.
   *Currently a deliberate software simplification (see `todo.md` P0-6).*
2. **Hardware trigger — real-hardware validation** — `EXTTRIGGER` is
   implemented for `finite_scan` (FastHeat / SlowMode), `ao_modulated`
   (IsoMode AC) and `start_ring_buffer`. Mock-tested in
   `test_fast_mode_with_hardware_trigger_runs_clean` and
   `test_iso_ac_with_hardware_trigger_runs_clean`. The loopback test on a
   real DAQ board (1 kHz square wave on AO ch1 → AI ch1, leading edge
   ≤ 1 sample) is still pending — `todo.md` P0-5.
3. **Slow mode in the GUI** — add a mode dropdown and reuse the existing
   profile editor. Backend (`select_mode("slow")`, `arm`, `run`) is already
   plumbed.

### Physical fidelity

4. **`ihtr1` value with the physicist** — production calibration must set
   `ihtr1 ≈ 1/R_shunt ≈ 5.88e-4` (S) so `ih = ihtr0 + ihtr1·V_shunt` is in
   amperes; the default identity `ihtr1 = 1.0` is dimensionally meaningless
   (test fallback). The Rhtr formula has been corrected to V/A = Ω
   (regression-tested by `test_rhtr_units_are_ohms_with_production_calibration`),
   so once `ihtr1` is set in `calibration.json` everything downstream is in
   physical units. Open as `todo.md` P0-3.
5. **AD595 Taux is averaged over the whole scan** — replace `df[3].mean()`
   in `apply_calibration` by either a per-sample correction or a
   low-pass-filtered trace. Drift over long slow ramps (>30 s) is
   O(0.5 °C) on lab-temperature changes. There is also a stub TODO at the
   same call site asking to expose an FFT spectrum of AI ch3 as a 50/60 Hz
   mains-pickup diagnostic.
6. **Temperature-to-voltage monotonicity** — when committing a new chip
   `Theater` polynomial, verify `dT/dV > 0` everywhere on
   `[0, safe_voltage]`. The current production polynomial
   `(-2.425, 8.04, -0.43)` has a tiny dip we tolerate via cumulative-max,
   but coefficient drift can widen it.
7. **AC bandwidth vs ramp rate (slow mode)** — the lock-in default
   `bandwidth = f / 5 = 7.5 Hz` corresponds to a settling time
   `~0.13 s`. For ramp rates above ~5 K/s the bandwidth starts smearing the
   `C_p(T)` curve. Make `bandwidth` an explicit `ModulationParams` field.
8. **Modulation clipping on slow/iso is silent** — the AC profile is
   `np.clip`'d to `[0, safe_voltage]` without a warning. With e.g.
   `DC=8.5 V, A=2 V, safe=9 V` half of the sine is clipped and the lock-in
   amplitude is biased silently. `todo.md` P1-4.
9. **AO buffer seamlessness at f_mod = 37.5 Hz** — `IsoMode.arm` logs a
   warning quantifying the defect, but the production fix (drop to a
   seamless `f_mod` such as 40 Hz, or expose the buffer length as a
   setting) is `todo.md` P0-4.
10. **Mock realism** — the mock copies AO voltage to AI ch5, scales it to
    put a small thermopile signal on ch1/ch4, and exposes ~25 °C on ch3. It
    does not simulate the chip's RC thermal response, so testing `C_p`
    reconstruction algorithms against the mock is not meaningful. Also
    injects a coherent ~196 Hz tone (todo.md P1-15).

### Code-quality

11. **Wildcard import `from pioner.shared.constants import *`** in
    `settings.py` and `front/mainWindow.py` makes refactors brittle.
    Replace by explicit imports.
12. **`mainWindow.fh_arm` profile cleanup** —
    `correctedProfile = uncorrectedProfile[:, :np.argmax(uncorrectedProfile[0])+1]`
    silently truncates the program at the first non-monotonic time. Should
    raise instead.

### Recently closed (2026-05-09 audit)

* Rhtr unit error (mΩ vs Ω in `apply_calibration`) — corrected.
* IsoMode DC-only bypass of calibration / `safe_voltage` — fixed.
* `AoDeviceHandler.set_voltage` / `.scan` now reject voltages outside the
  configured analog range.
* `ExperimentManager.stop()` now stops AO before AI.
* Default `Modulation.Offset` now `0.0 V` (was a hidden 0.3 V DC bias).
* `_collect_finite_ai` rejects odd `sample_rate` instead of crashing in
  `np.reshape`.
* `Tango.set_sample_scan_rate` validates the integer (positive, even,
  ≤ `MAX_SCAN_SAMPLE_RATE`).
* `hardware_trigger` now applied to iso/slow CONTINUOUS paths
  (`ao_modulated` + `start_ring_buffer`), not only `finite_scan`.

---

## 9. Test matrix

| Test file                    | Coverage                                                                                                                                  |
|------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `test_calibration.py`        | identity, clamping, vectorised round-trip, error paths, production polynomial inverts                                                     |
| `test_modulation.py`         | `apply_modulation`, lock-in amp/phase, FFT demod (1f/2f/3f, aliasing, leakage), AO period integrity (seamless / 37.5 Hz defect / aliased) |
| `test_mock_uldaq.py`         | lifecycle, shared buffer, scan progression, race-free re-arm                                                                              |
| `test_modes_e2e.py`          | fast / slow / iso end-to-end on mock; temp-program path; validation errors; iso DC temp goes through calibration (regression for #2);    |
|                              | `ao_set` rejects out-of-range voltages (regression for #5); iso AC honours `hardware_trigger` (regression for #3); iso `stop()` early    |
| `test_apply_calibration.py`  | `Uref` tiling for iso, `Thtr` NaN-when-idle, raw-column drop, empty-input, **Rhtr units in Ω with production calibration** (regression for #1) |

```bash
PYTHONPATH=src .venv/bin/pytest tests/              # 52 tests, ~11 s
PYTHONPATH=src .venv/bin/python -m pioner.back.debug   # smoke test all 3 modes
```

The mock-specific tests are skipped when a real `uldaq` driver is detected
(no env-var needed; the dispatcher checks `DAQ_AVAILABLE` at import time).

---

## 10. Key physics formulas (reference card)

All formulas below are what `apply_calibration` and the mode classes
actually compute, with units pinned. Identifiers match the code.

### Heater drive — temperature → voltage (FastHeat / SlowMode / IsoMode)

```
V_drive(t) = T_to_V_inv(T_user(t))      [V, in [0, safe_voltage]]

V_drive_AC(t) = clip(V_drive(t) + offset + A·sin(2π·f·t),
                     0, safe_voltage)   [V, slow / iso AC]
```

`T_to_V_inv` numerically inverts the cubic `T(V) = θ0·V + θ1·V² + θ2·V³`
on a 90 000-point grid (`pioner.shared.utils.temperature_to_voltage`).
`A = ModulationParams.amplitude`, `offset = ModulationParams.offset`,
`f = ModulationParams.frequency`.

### Engineering units (apply_calibration)

```
Taux       = AD595_correct(100 · mean(U_AI3))                        [°C]

Utpl_mV    = U_AI4 · 1000 / Gain_Utpl                                [mV]
T          = ttpl0·(Utpl_mV + utpl0) + ttpl1·(Utpl_mV + utpl0)² + Taux   [°C]

Umod_mV    = U_AI1 · 1000 / Gain_Umod                                [mV]
T_hr       = ttpl0·(Umod_mV + utpl0) + ttpl1·(Umod_mV + utpl0)²      [°C]

Ihtr       = ihtr0 + ihtr1·U_AI0                                     [A]
Rhtr       = (U_AI5 - U_AI0 + uhtr0)·uhtr1 / Ihtr                    [Ω]
Thtr       = thtr0 + thtr1·(Rhtr + thtrcorr) + thtr2·(Rhtr + thtrcorr)²  [°C]
              (NaN where |Ihtr| < 1 nA — heater idle)
```

`U_AI{0,1,3,4,5}` are raw AI samples in **volts**. `Gain_Utpl=11`,
`Gain_Umod=121` from the `Hardware` calibration block. `ihtr1` must be
`1/R_shunt ≈ 5.88e-4 S` in production for `Ihtr` to be in amperes (see §8
item 4).

### Lock-in (time-domain, `lockin_demodulate`)

```
in_phase(t)   = signal(t) · sin(2π·f·t)
quadrature(t) = signal(t) · cos(2π·f·t)
{I_lp, Q_lp}  = sosfiltfilt(Butter4, Wn=(f/5)/(fs/2), {in_phase, quadrature})
amp(t)        = 2·sqrt(I_lp² + Q_lp²)                       [same units as signal]
phase(t)      = -arctan2(Q_lp, I_lp)                        [rad in (-π, π]; +ve = lag]
```

Default `bandwidth = f / 5`, settling time ≈ `5/(2π·bandwidth) ≈ 0.13 s`
at `f = 37.5 Hz` (see todo item 7).

### FFT demodulation (iso AC, `fft_demodulate`)

For a stationary signal sampled at `fs` over an integer-cycle slice of length
`N`:

```
X = rfft(signal[start:])                                    # N samples
A_h    = 2 · |X[h·k_f]| / N                                 [units of signal]
phi_h  = wrap(-π/2 - arg(X[h·k_f]) + h·ω·t_start)           [rad in (-π, π]]
leakage = 1 - Σ_h |X[h·k_f]|² / Σ_k |X[k]|²                 [dimensionless]
```

with `k_f = N·f/fs` (integer by construction), `ω = 2π·f`,
`t_start = (len(signal) − N) / fs` so the recovered phase is referenced to
sample 0 of the original input. Harmonics 1f / 2f / 3f extracted at no
extra cost; aliased harmonics (`h·f ≥ fs/2`) return `NaN`.

### AO buffer integrity (CONTINUOUS replay, `check_ao_period_integrity`)

```
cycles          = N · f / fs
cycles_drift    = cycles - round(cycles)                   [cycles]
phase_jump_rad  = 2π · cycles_drift                        [rad per wrap]
seamless        = (|phase_jump_rad| < 1e-3) and not aliased
```

At the default `f_mod = 37.5 Hz`, `fs = 20 kHz`, `N = 20 000`:
`cycles = 37.5`, `phase_jump_rad ≈ ±π` ⇒ NOT seamless. `IsoMode.arm`
logs a warning with `cycles_drift`, `phase_jump_rad`, and FFT leakage.

### Heat capacity (sketch, not implemented in pipeline)

For reference — what the demodulated AC observables encode:

```
P_AC     = V_AC · I_AC · cos(phi_drive)                     [W]
C_p(T)   ~ P_AC / (ω · ΔT_AC) · cos(phi_response)           [J/K]
```

`P_AC` from heater drive (slow ramp T-axis), `ΔT_AC` from `temp-hr_amp`,
`phi_response` from `temp-hr_phase`. Production C_p reduction lives outside
this back-end (downstream analysis code).
