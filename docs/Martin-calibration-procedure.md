# Martin's calibration procedure for PIONER nanocalorimeter chips

Translated from `Martin-calibration-procedure.docx` (Russian original by
Martin). This document records the legacy IgorPro-based workflow as
written, then maps each step onto the current PIONER code base and onto
the planned live-streaming / calibration wizard architecture
(`live-streaming.md`).

The wording in section 2 is intentionally close to Martin's original so
operators can follow it side-by-side with the docx. Section 3 onwards is
PIONER-side commentary.

---

## 1. Glossary (Martin's notation -> PIONER fields)

| Martin       | Meaning                                                    | PIONER code                                          |
|--------------|------------------------------------------------------------|------------------------------------------------------|
| `direct.ini` | identity (passthrough) calibration file, all 0s and 1s     | `src/pioner/settings/default_calibration.json`       |
| `Rhtr`       | heater resistance from chip datasheet (Xensor site)        | `Calibration.rhtr` / `"R heater"` JSON field         |
| heater safe voltage | max DC voltage allowed on the heater AO line        | `Calibration.safe_voltage` / `"Heater safe voltage"` |
| Input gains 1, 2, 10, 2 | front-end IA gains on AI channels              | `Hardware.gain_utpl`, `Hardware.gain_umod` (see notes)|
| Sampling rate 20000 | AI sample rate, Hz                                  | `config.json` AI sample rate (production: 20 kHz)    |
| `Uhtr`       | voltage across heater (AO drive minus shunt drop)          | computed inside `apply_calibration`, V               |
| `Uref`       | commanded AO voltage on heater channel                     | `Uref` column produced by `apply_calibration`        |
| `Utpl`       | thermopile voltage, standard (low-gain) channel            | `Utpl` AI ch + `Calibration.utpl0`                   |
| `Umod`       | thermopile voltage, high-gain modulation channel           | `Umod` AI ch                                         |
| `Ihtr`       | heater current (= shunt voltage / `R_shunt`)               | `ihtr0 + ihtr1 * V_shunt`, A                         |
| `Thtr`       | heater temperature from heater R, standard polynomial       | `Calibration.thtr0..thtr2`, `thtrcorr`               |
| `Thtrd`      | heater temperature from differential heater, polynomial    | `Calibration.thtrd0..thtrd2`, `thtrdcorr`            |
| `Ttpl`       | sample temperature from thermopile                         | `Calibration.ttpl0..ttpl1` (uses `Utpl` and `Taux`)  |
| `Taux`       | cold-junction (AD595) reference temperature                | computed in `apply_calibration` from AI ch3          |
| `Theater(Uheater)` | T_heater as polynomial of AO heater voltage          | `Calibration.theater0..theater2` (poly 3, no const)  |
| `Thtr(Utpl)` | AC amplitude correction: T amplitude as poly of Utpl       | `Calibration.ac0..ac3` (`"Amplitude correction"`)    |
| `_amp`       | AC modulation amplitude after lock-in demodulation         | `lockin_demodulate` amplitude output                 |
| Modulation: f=37.5 Hz, A=0.1 V, off=0.3 V | calibration AC drive params       | `config.json` modulation defaults (production)       |
| `reset!!!`   | DAQ device reset before arming the calibration drive       | `daq_device.DaqDevice.reset()`                       |
| `On => Continue => Continuous` (no `->0<-`) | start AC monitoring drive WITHOUT zeroing AO | IsoMode / "monitoring drive" of `live-streaming.md` |
| `->0<-`      | UI button that drops AO to 0 V (and Utpl offset to zero)   | `ttplBoxResetButton` / `uhtrBoxResetButton` in IR UI |
| `Utpl ->`    | "press arrow in top-right of calibration window": sets    | writes `utpl0` so that current Utpl reading -> 0     |
|              | the current Utpl reading as the new zero offset            |                                                       |
| IgorPro      | external analysis tool used to fit and pick onsets         | replaced by the planned PIONER calibration wizard    |

A small notation caveat: the Russian text writes the differential-heater
temperature as `Thtrd` (sometimes `_Thtrd`), which matches the JSON key
`Thtrd` and the column produced by `apply_calibration`.

---

## 2. Procedure (one-to-one translation)

Prerequisites: chip mounted, leads connected, DAQ powered on, software
launched in calibration mode, AC modulation disabled at start.

1. **Load a passthrough calibration file** (`direct.ini` -- in PIONER,
   `default_calibration.json`) so all polynomials are identity. Then
   enter the chip's nominal **heater safe voltage** and nominal
   **`Rhtr`** (both from the Xensor product page for this chip). Press
   **Apply**.
2. **Input gains:** 1, 2, 10, 2 (front-end IA gains on the AI channels --
   see "Discrepancies" below for the channel order).
3. **Sampling rate:** 20000 (Hz).
4. **Modulation parameters:** frequency f = 37.5 Hz, amplitude A = 0.1 V,
   offset = 0.3 V.
5. **Press Reset.** (DAQ device-level reset.)
6. **Apply calibrant particles to the chip.** Preferably arranged in a
   single line, parallel to the heater stripes.
7. **Start the AC monitoring drive:** On -> Continue -> Continuous.
   **Do NOT press `->0<-`** -- the Utpl-zero shortcut must stay
   un-pressed at this point; the absolute thermopile reading is the
   information of interest.
8. **Sanity check** the Scope panel readings. In particular, `Thtr` and
   `Thtrd` should not differ significantly. If they do, stop and
   diagnose the chip / cabling.
9. **Run a ramp** -- either a temperature ramp or a voltage ramp -- from
   0 to the maximum allowed heater voltage. Export it to IgorPro.
10. **Plot** `_amp vs _Thtr` and `_amp vs _Thtrd`. From these plots,
    pick the AC-amplitude features at each calibrant melting onset and
    build the following table:

    | Reference temperature | First column (`_Thtr` at the feature) | Second column (`_Thtrd` at the feature) |
    |-----------------------|---------------------------------------|------------------------------------------|
    | Room temperature      | first `_Thtr` sample of the ramp      | first `_Thtrd` sample of the ramp        |
    | Melt T of calibrant #1| `_Thtr` at the melting onset          | `_Thtrd` at the melting onset            |
    | ...                   | ...                                   | ...                                      |

11. **Fit column 2 vs column 1, and column 3 vs column 1**, with a
    degree-3 polynomial (poly 3). Enter the resulting coefficients into
    the calibration window for `Thtr` and `Thtrd`. **Apply -> Save.**
12. **Run a voltage ramp** from 0 to the maximum allowed heater voltage.
    Export to IgorPro.
13. **Plot `Thtrd vs Uhtr`**, fit with **poly 4**, and write the
    coefficients **k1, k2, k3** into the `Theater(Uheater)` field. (k0
    is intentionally dropped; T = 0 at U = 0.) **Apply -> Save.**
14. **Turn the modulation off.**
15. After `Utpl` settles, press the **arrow button in the upper-right
    corner of the calibration window** -- this latches the current
    (settled) `Utpl` value as the new `Utpl` zero offset. **Apply -> Save.**
16. **Turn the modulation back on.** Run a **temperature ramp** from 0 to
    the maximum allowed temperature at **10-20 deg C/min**.
17. In the Graph window, open the **Calibration** tab, select
    **`Thtr(Utpl)`**, fit by polynomial, store the coefficients (this
    is the AC amplitude correction).
18. **Verify**: re-run any ramp and check that the calibrant melting
    peaks land at their known temperatures.

---

## 3. Mapping onto current PIONER code

PIONER does not yet have a calibration wizard UI, but each step's data
flow lands on existing primitives. The mapping below is grouped by
output coefficient set.

### 3.1 Step 1 -- bootstrap and chip-specific constants

- "Load `direct.ini`" = `Calibration().read("src/pioner/settings/default_calibration.json")`
  in [src/pioner/shared/calibration.py:164](../src/pioner/shared/calibration.py#L164).
  The file ships pre-populated with identity polynomials; see
  [src/pioner/settings/default_calibration.json](../src/pioner/settings/default_calibration.json).
- "Enter heater safe voltage" -> `Calibration.safe_voltage` (JSON key
  `"Heater safe voltage"`). This value is the clamp applied by
  `temperature_to_voltage` [src/pioner/shared/utils.py:63](../src/pioner/shared/utils.py#L63)
  and by `SlowMode`/`IsoMode` after summing the AC drive
  [src/pioner/back/modes.py:569](../src/pioner/back/modes.py#L569).
- "Enter `Rhtr`" -> `Calibration.rhtr` (JSON key `"R heater"`).
  Currently informational; the heater R used downstream in `Thtr` is
  computed sample-by-sample from V and I (see 3.3), not from this
  constant.

### 3.2 Step 2-4 -- input gains, sampling rate, AC drive

- "Input gains 1, 2, 10, 2": these are the IA gains for the AI input
  stage. PIONER currently exposes only two of them --
  `Hardware.gain_utpl` (default 11.0) and `Hardware.gain_umod`
  (default 121.0) -- consumed inside `apply_calibration` at
  [src/pioner/back/modes.py:224](../src/pioner/back/modes.py#L224) and
  [src/pioner/back/modes.py:231](../src/pioner/back/modes.py#L231). Martin's
  "1, 2, 10, 2" probably refers to the older 4-channel front-end and
  needs explicit mapping (see Discrepancies).
- "Sampling rate 20000": the production AI sample rate. Already aligned
  with `live-streaming.md` section 1 ("production config: 20 kHz, 6
  single-ended channels"). Lives in `config.json`.
- "f = 37.5 Hz, A = 0.1 V, off = 0.3 V": modulation parameters for the
  calibration AC drive. These are exactly the defaults stated in
  `live-streaming.md` section 4 for the idle "monitoring AC drive", and
  are loaded via `ModulationParams` from `shared/modulation.py`.

### 3.3 Steps 9-11 -- `Thtr` and `Thtrd` polynomials (R -> T)

This is the path computed by `apply_calibration` at
[src/pioner/back/modes.py:253-276](../src/pioner/back/modes.py#L253-L276):

```
ih       = ihtr0 + ihtr1 * V_shunt              # A (production ihtr1 ~= 1/R_shunt)
R_heater = (V_AO - V_shunt + uhtr0) * uhtr1 / ih  # Ohm  (NaN when |ih|<1e-9)
Thtr     = thtr0 + thtr1*(R + thtrcorr) + thtr2*(R + thtrcorr)^2
Thtrd    = (same shape with thtrd0..thtrd2)
```

So Martin's "fit `_amp vs _Thtr` table with poly 3" produces
`thtr0, thtr1, thtr2` (plus `thtrcorr` if used), written into the JSON
fields `"Thtr": {"0", "1", "2", "corr"}` and `"Thtrd": {...}` -- see
[src/pioner/shared/calibration.py:189-197](../src/pioner/shared/calibration.py#L189-L197).

The `_amp` signal Martin plots is the AC amplitude from the lock-in. In
PIONER this is the amplitude output of
[`lockin_demodulate`](../src/pioner/shared/modulation.py#L121) (or the
sliding-window demod described in `live-streaming.md` section 2),
applied to the `Umod` thermopile trace at f = 37.5 Hz.

### 3.4 Steps 12-13 -- `Theater(Uheater)` polynomial (U -> T)

This produces the inverse map used by `temperature_to_voltage` (chip-T
program -> AO voltage) and by `_add_params` to derive `max_temp`:

```
T = theater0*U + theater1*U^2 + theater2*U^3
```

See [src/pioner/shared/calibration.py:140-143](../src/pioner/shared/calibration.py#L140-L143)
and [src/pioner/shared/utils.py:64-67](../src/pioner/shared/utils.py#L64-L67).

Martin says "fit poly 4, write k1, k2, k3". Our model is poly 3 in U
with no constant term, which matches Martin once you drop k0 (k0 ~= 0
by construction: T(U=0) = 0). The PIONER coefficient `theater0`
corresponds to Martin's `k1`, `theater1` to `k2`, `theater2` to `k3`.
The "field index off by one vs. fit order" is a naming hazard worth
flagging in any future wizard UI.

### 3.5 Steps 14-15 -- `utpl0` zero offset

`Calibration.utpl0` is the additive offset applied to `Utpl` (and to
`Umod`) before the `Ttpl` polynomial:

```
Utpl_corrected = (AI_ch * 1000 / gain_utpl) + utpl0
temp           = ttpl0 * Utpl_corrected + ttpl1 * Utpl_corrected^2
```

See [src/pioner/back/modes.py:223-235](../src/pioner/back/modes.py#L223-L235).
"Press the arrow after Utpl settles" = capture the current measured
`Utpl` (in mV) with the sign flipped and store it in `utpl0`. There is
**no helper in the back-end today that performs this latch**; today it
is purely a UI action (legacy IR UI has the button on
`ttplBoxResetButton` at [pioner-IR-branch/pioner_app/ui/h_windows.py:101](../pioner-IR-branch/pioner_app/ui/h_windows.py#L101)).
A back-end equivalent would be a one-line call that sets
`calibration.utpl0 = -mean_Utpl_mV_over_last_K_samples`.

### 3.6 Steps 16-17 -- `Thtr(Utpl)` amplitude correction

The "Amplitude correction" coefficients (`ac0..ac3`, JSON key
`"Amplitude correction"`) are loaded by `Calibration.read` at
[src/pioner/shared/calibration.py:209-212](../src/pioner/shared/calibration.py#L209-L212),
but **they are not yet consumed by `apply_calibration`** -- there is no
call site that applies them to the lock-in amplitude. This is the
"correct AC amplitude as a function of `Utpl`" step Martin describes.
This is a known gap to surface to the wizard / streaming work.

### 3.7 Step 18 -- verification

Re-running any ramp and checking peak positions is the manual analogue
of an automated "calibration verification" run. Today this is operator
work; tomorrow it could be a final stage of the wizard that picks peaks
from the live demod amplitude and prints residuals vs. known
calibrant temperatures.

---

## 4. How this lines up with `live-streaming.md`

`live-streaming.md` already pencils in a "Calibration" mode in section 7
("Per-mode behaviour summary"):

> Calibration: CONTINUOUS AI, AO = "Three-stage drive per
> `CalibrationWizard` (V ramp or T ramp; AC may or may not be present
> per stage)", DiskRecorder active per stage, "Cursor-pick plot during
> each stage".

Martin's procedure is *the* concrete instance that fills in those three
stages. Mapped onto the streaming architecture:

| Wizard stage | Martin steps | AO drive                                | Modulation | Output coefficients          |
|--------------|--------------|------------------------------------------|------------|------------------------------|
| A. Calibrant fits | 6-11    | V or T ramp 0 -> Vmax                    | ON (f=37.5, A=0.1, off=0.3) | `Thtr.{0,1,2,corr}` and `Thtrd.{0,1,2,corr}` |
| B. T(U) map       | 12-13   | V ramp 0 -> Vmax                         | ON (same)  | `Theater.{0,1,2}` (= k1, k2, k3) |
| C. Utpl zero      | 14-15   | DC monitoring drive (or AO held)         | OFF        | `Utpl.0` (= `utpl0`)         |
| D. AC correction  | 16-17   | T ramp 0 -> Tmax at 10-20 deg C/min      | ON (same)  | `Amplitude correction.{0..3}` (= `ac0..ac3`) |
| E. Verify         | 18      | any ramp                                 | ON         | (no fit, sanity only)        |

Concrete consequences for the live-streaming work:

1. **AI stays CONTINUOUS the whole way.** All five wizard stages just
   change AO state and modulation on/off. The persistent AI ring buffer
   (`live-streaming.md` section 3, Rule 1) means the operator can scrub
   between stages without restarting AI, which avoids the 100-500 ms
   gap problem.
2. **The AC defaults in `live-streaming.md` section 4 are exactly
   Martin's calibration drive.** `idle / monitoring AC drive` and
   "calibration stage A drive" are the same waveform with the same
   parameters. No special-cased calibration AC config is needed.
3. **DiskRecorder per stage.** Each of stages A, B, D produces a ramp
   that today is exported to IgorPro and fit by hand. With the
   recorder, the HDF5 file produced by the stage *is* the input to the
   fit; the wizard's "Pick onsets / fit poly N" step can run on the
   recorded data immediately. Stage E reuses the same recorder path.
4. **`->0<-` button and "arrow" button are different things.** Martin
   warns at step 7 not to press `->0<-` (UI shortcut that zeroes the AO
   monitoring drive; would kill the AC modulation needed for stage A).
   Step 15's "arrow in the calibration window" latches the current
   `Utpl` as the new `utpl0` offset. The wizard UI should make these
   two actions visually unambiguous (different icons, separate panes)
   to avoid the legacy ambiguity.
5. **"Cursor-pick plot during each stage" (section 7 of
   live-streaming.md) maps to**:
   - Stage A: click melting onsets on `_amp` vs `Thtr` / `_amp` vs
     `Thtrd`.
   - Stage B: ranges over `(Uhtr, Thtrd)` for the poly-4 fit.
   - Stage D: ranges over `(Utpl, _amp)` for the AC correction fit.
6. **CalibrationWizard is the natural owner of `utpl0` latching and
   "Apply -> Save"** flows on the JSON file -- both Martin's step 15
   and his repeated `Apply -> Save` cadence.
7. **Live-streaming sections 2 and the sliding-window demod** are what
   produce Martin's `_amp` trace in real time. Without
   live-streaming, today the operator gets `_amp` only after the run
   completes (FastHeat-style block output). With live-streaming, the
   wizard can show the cursor-pick plot updating during the ramp,
   which is what Martin's workflow assumes IgorPro will give him.

---

## 5. Discrepancies and open questions

These are points where Martin's procedure does not map cleanly onto the
current code and a decision is needed before the calibration wizard is
implemented.

1. **Input-gain channel order.** Martin lists four gains `1, 2, 10, 2`.
   PIONER currently has two named gains (`gain_utpl = 11.0`,
   `gain_umod = 121.0`) and assumes single-ended USB-2637 with 6 AI
   channels (`live-streaming.md` section 1). The Martin numbers are
   most likely the old four-channel hardware (Uref, Umod, Utpl, Uhtr or
   similar). Need clarification before the wizard exposes a "gains"
   panel: are these gain *settings* on programmable amps that we still
   set per run, or are they fixed in the front-end and we just need to
   record them for traceability?
2. **`Theater(U)` polynomial degree.** Martin fits poly 4 and writes 3
   coefficients (k1..k3, drops k0). Our `Calibration.theater0..2`
   already matches that, but the field naming (`theater0` = k1, etc.)
   is a footgun for anyone hand-editing the JSON. Either rename to
   `theater_k1, theater_k2, theater_k3` or add a comment in the JSON
   `"Info"` field.
3. **`Amplitude correction` is loaded but unused.** `Calibration.ac0..ac3`
   is parsed from JSON but never consumed by `apply_calibration` or
   `lockin_demodulate`. Step 17 produces these coefficients but PIONER
   has no code path that applies them. Either implement the correction
   (the natural place is to scale the lock-in amplitude by a
   poly-3(Utpl)) or document that today these coefficients are
   informational only.
4. **No back-end helper for the `utpl0` latch (step 15).** Today this
   is a UI-only operation in the IR branch. Need a small back-end
   function `Calibration.zero_utpl_from_samples(samples_mV)` that
   computes the mean of a settled window and stores `-mean` in
   `utpl0`.
5. **No back-end helper for the chip-validity sanity check (step 8).**
   "`Thtr` and `Thtrd` should not differ much" is a quantitative test
   that fits naturally into the between-experiment chip monitoring
   layer described in `live-streaming.md` section 1. Could be a
   threshold (e.g., `abs(Thtr - Thtrd) < 5 deg C` at room T).
6. **Calibrant table is an operator-managed list.** Martin lists "first
   row = room temperature, first sample" plus "one row per calibrant
   melt onset". The wizard needs a small UI for entering the known
   melting temperatures of the calibrants the operator actually put on
   the chip (step 6). Today no such table exists in PIONER.
7. **Order of stages B and C is unusual.** Step 14 turns modulation
   off before step 15 sets `utpl0`, then step 16 turns modulation back
   on. The intent is to capture the AC-free Utpl baseline. The wizard
   should encode this explicitly (modulation OFF for stage C, ON for
   the rest) so the operator cannot accidentally measure `utpl0` with
   modulation still running.
8. **The "10-20 deg C/min" ramp in step 16** is slow enough that the
   AD595 cold-junction averaging used by `apply_calibration` (today
   `df["Taux"] = mean(AD595)` over the full scan) introduces the
   ~0.5 deg C drift error already flagged in
   [src/pioner/back/modes.py:206](../src/pioner/back/modes.py#L206)
   and in `CLAUDE.md`. For a long calibration ramp this is
   non-trivial. Worth deciding whether to switch to per-sample (or
   low-pass-filtered) AD595 before running stage D for real.

---

## 6. Source

Original document: [Martin-calibration-procedure.docx](Martin-calibration-procedure.docx).
The Russian original is retained as the canonical source; this English
file is the working reference.
