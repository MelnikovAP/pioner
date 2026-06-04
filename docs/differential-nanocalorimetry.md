# Differential nanocalorimetry: dual-area chips and dual-chip carriers

Design notes for moving PIONER from one heater + one thermopile pair per
experiment to either (a) a chip with two calorimetric areas
(sample + reference) or (b) two chips wired into the same DAQ board, or a
combination of both.

This document is an architectural survey: it captures what is feasible on
the current hardware, what changes in the firmware/software, and the
checklist of things that must not be forgotten before committing to a
design. No code is changed.

Related references:
- [usb-2637-vs-2627.md](usb-2637-vs-2627.md) - DAQ envelope
- [Bondar-uCal.md](Bondar-uCal.md) - prior C++ design conventions
- [live-streaming.md](live-streaming.md) - streaming / ring-buffer architecture
- [../CLAUDE.md](../CLAUDE.md) - load-bearing physics / unit rules
- [ir-merge-answers.md](ir-merge-answers.md) - consolidated Q&A from
  the IR-branch developer; the JSON program schema is still in flux

---

## TL;DR

Both ideas are feasible on the current USB-2637. The DAQ board has plenty
of headroom on analog inputs (64 SE channels available, ~6 used today)
and on aggregate throughput (1 MS/s vs ~120 kS/s today). The real
bottlenecks are:

1. **Analog outputs.** The board has only 4 AO channels. Independent
   drive of more than two heaters consumes all of them and leaves no
   room for the trigger AO.
2. **Analog front-end.** Every heater needs its own shunt resistor,
   summing amplifier, and (likely) its own thermopile pre-amp chain.
   Doubling or quadrupling this is a board-level rework, not a firmware
   change.
3. **Calibration.** Each calorimetric area needs its own polynomial set
   (T(V_htr), AD595 correction, ihtr0/ihtr1, safe_voltage). The current
   `Calibration` object assumes a single area.
4. **Software.** All channel constants in
   [src/pioner/shared/channels.py](../src/pioner/shared/channels.py) are
   scalars, and `apply_calibration` in
   [src/pioner/back/modes.py:180](../src/pioner/back/modes.py#L180) reads
   fixed column names. The JSON program schema, HDF5 layout, Tango pipe,
   and GUI all assume a single channel.

DAQ-wise, two chips with one heater each (or one chip with two areas) is
the comfortable case. Four independent heaters (two chips, two areas
each) fits but consumes every AO channel.

---

## 1. Current single-channel baseline

One "measurement channel" today equals: 1 heater + 1 shunt resistor +
1 high-gain thermopile (Umod) + 1 standard thermopile (Utpl) + a board-
wide AD595 cold-junction reference.

Channel layout (see
[channels.py:29-41](../src/pioner/shared/channels.py#L29-L41)):

| Channel | Role                                  |
|---------|---------------------------------------|
| AO ch0  | Shunt-path bias (~0.1 V)              |
| AO ch1  | Heater drive (DC + AC)                |
| AO ch2  | Guard heater / hardware trigger       |
| AO ch3  | Spare                                 |
| AI ch0  | V_shunt (heater current proxy)        |
| AI ch1  | Umod (high-gain thermopile)           |
| AI ch3  | AD595 cold-junction                   |
| AI ch4  | Utpl (standard thermopile)            |
| AI ch5  | V_heater feedback                     |

DAQ envelope (USB-2637, from
[usb-2637-vs-2627.md](usb-2637-vs-2627.md)):

- 4 AO, 16-bit, +/-10 V, 1 MS/s
- 64 SE AI, 16-bit, +/-10 V, 1 MS/s aggregate
- AI FIFO: 4 kS
- AI/AO pacers (XAPCR / XDPCR) are independent
- AI crosstalk (adjacent channels, DC to 10 kHz): -80 dB

The whole pipeline is hard-coded to this single-area topology in
`channels.py`, `modes.apply_calibration`, the JSON program schema, the
HDF5 group layout, and the GUI.

---

## 2. Three architectural options

### Option A: sample + reference on one chip, symmetric drive

One AO drives both heaters in parallel (or through a matched resistor
split). Acquisition collects the differential thermopile signal
S - R either in analog (instrumentation amp) or in software.

- **AO usage:** unchanged (1 logical heater channel).
- **AI usage:** +2 channels for Umod_R and Utpl_R (or +1 if the
  subtraction is done in analog).
- **Pros:**
  - Minimal AO impact.
  - Classical DSC topology; common-mode drifts (cold-junction shifts,
    50/60 Hz pickup, slow electronics drift) cancel in S - R.
  - Single AC modulation, single lock-in reference - no
    re-derivation of the lock-in pipeline.
- **Cons:**
  - No power-compensated operation (cannot drive S and R with
    different power).
  - Any R_htr mismatch between the two areas converts directly into a
    differential power offset, which masquerades as a signal.
  - Still need per-area thermal calibration.

### Option B: sample + reference on one chip, independent drive

Separate AO per area. Enables power-compensated DSC: control loop keeps
T_S == T_R, the measured quantity is the differential drive power.

- **AO usage:** ch1 (S), ch2 (R), ch0 bias, ch3 trigger -- **all four
  AO channels consumed.** No spare.
- **AI usage:** +4 to +5 channels (V_shunt_R, Umod_R, Utpl_R, V_htr_R,
  optionally a second AD595 if the chip is not in a single thermal
  enclosure with the existing one).
- **Pros:**
  - Power-compensated operation is possible.
  - Each area can be characterized independently, including
    asymmetric R_htr or thermopile gain.
- **Cons:**
  - Consumes the entire AO bank. If an external hardware trigger is
    later required, it must be moved to a DIO or counter line.
  - Twice the calibration data per chip.
  - Two AOs sharing the same pacer is fine, but the new control loop
    (matching T_S to T_R) is non-trivial -- this is a closed-loop
    feature, not a passive measurement.

### Option C: two independent chips on the same board

Same channel arithmetic as Option B, but the two AOs now drive two
*different chips* instead of two areas on one chip.

- 2 chips x 1 area each: identical AO/AI footprint to Option B.
  Fully feasible.
- 2 chips x 2 areas each (Option B + Option C): 4 independent
  heaters require 4 AO drive channels. On USB-2637 that fits only if
  the bias AO is moved into hardware (fixed voltage divider) and the
  trigger AO is moved to DIO/CTR. **Feasible but no margin.**

---

## 3. What to keep in mind

### 3.1 Electronics and physics

1. **S<->R thermal isolation on a single chip.** The differential
   measurement only works if the two areas are thermally symmetric.
   Any heat leak from S into R pollutes the differential signal. This
   is a chip-geometry question, not a software question.
2. **Chip<->chip thermal isolation in the dual-chip holder.** If the
   two chips are not in a common thermal enclosure they will see
   different cold-junction temperatures, which biases the thermopile
   baseline.
3. **R_htr variability between areas / chips.** Manufacturing spread is
   commonly 5-20 %; the same drive voltage delivers different power.
   This must be measured per area and used in calibration.
4. **Per-heater shunt resistor.** Without it the current cannot be
   measured. ihtr0/ihtr1 must be calibrated per shunt per area (see
   the "Calibration dimensions" rule in [../CLAUDE.md](../CLAUDE.md):
   `ihtr1 ~ 1/R_shunt`, so production R_shunt ~ 1700 Ohm implies
   ihtr1 ~ 5.88e-4; identity `ihtr1 = 1.0` is the test fallback only
   and must not propagate into a multi-area config).
5. **Per-AO safe-voltage clamp.** The warning at
   [modes.py:167-172](../src/pioner/back/modes.py#L167-L172) and the
   `np.clip(..., safe_voltage, ...)` calls at
   [modes.py:435-439](../src/pioner/back/modes.py#L435-L439) and
   [modes.py:569](../src/pioner/back/modes.py#L569) currently take a
   single scalar from `calibration.safe_voltage`. With multiple
   heaters each AO buffer must be clipped against its own
   safe_voltage before write.
6. **AD595 cold-junction.** A single AD595 is enough if both chips
   (or both areas) sit in a common thermally stabilized enclosure.
   If they are physically separated, add a second AD595 -- the AI
   board has the channels free. The polynomial correction below
   -12 degC ([../CLAUDE.md](../CLAUDE.md): "AD595 cold-junction")
   stays unchanged per probe.
7. **AO pacer synchrony.** All AO channels on USB-2637 run from a
   single XDPCR pacer, so heaters driven from different AO channels
   are sample-locked by construction. This is the desirable property
   for shared AC modulation and lock-in demodulation.
8. **AI crosstalk.** -80 dB at DC-10 kHz is fine, but the
   single-ended scan list order matters. Adjacent channels can
   couple slightly more than non-adjacent ones; place the most
   sensitive (Umod_S, Umod_R) away from the noisy AO feedback
   channels in the scan list.
9. **FIFO depth and OVERRUN margin.** The 4 kS AI FIFO
   ([usb-2637-vs-2627.md:219-227](usb-2637-vs-2627.md#L219-L227))
   today gives ~34 ms of stall tolerance at 6 ch x 20 kHz. With
   12 channels at 20 kHz the margin drops to ~17 ms; with 24 channels
   to ~8.5 ms. Adopting `ScanOption.DEFAULTIO` from the IR branch is
   strongly recommended at that point (see
   [../known-issues.md](../postmortem/2026-05-23-fifo-overrun-continuous-ai.md) section 1 for the prior
   OVERRUN incident).
10. **Trigger AO.** Options B and C consume the AO bank. If an
    external trigger is still needed, move it to a DIO pin or to one
    of the four counter/timer outputs -- both are unused today.

### 3.2 Lock-in and AC modulation

11. **Common modulation, shared reference.** If both heaters carry
    the same AC modulation frequency and phase (Option A, or
    Option B with a shared modulation pattern), one lock-in reference
    works for both areas and no new 2f-leakage paths appear.
12. **Distinct modulation frequencies per area.** If the design needs
    different f_mod per area (sometimes used to decouple the two
    channels), then each area needs its own reference and its own
    integer-cycle window inside `lockin_demodulate`. Both frequencies
    must remain strictly below Nyquist
    (`f_mod < ai_sample_rate / 2`, see
    [../CLAUDE.md](../CLAUDE.md): "AC modulation + software
    lock-in").
13. **Shunt voltage as reference.** The Bondar C++ code used the
    per-heater V_shunt as the lock-in reference (a current proxy):
    see [Bondar-uCal.md:319-321](Bondar-uCal.md#L319-L321). For
    multi-area work, "own shunt = own reference" is cleaner than
    taking the AO command as the reference, because it accounts for
    cable / amplifier phase shifts in each chain.

### 3.3 Software

14. **`channels.py` constants are scalar.** All of `HEATER_AO`,
    `HEATER_CURRENT_AI`, `UMOD_AI`, `UTPL_AI`, `UHTR_AI` must become
    indexable per area (list or dict keyed by `area_id`/`chip_id`).
    See [channels.py](../src/pioner/shared/channels.py).
15. **JSON program schema.** The current `{"ch1": {...}}` shape
    needs to generalize to multiple areas. Note that there is
    already an open question about competing schemas between this
    branch and the IR branch
    ([ir-merge-answers.md](ir-merge-answers.md)); the dual-area
    schema should be decided jointly with that merge, not bolted on
    afterwards.
16. **Calibration object.** Today `Calibration` is a single object
    per experiment. It needs to become a collection keyed by
    area/chip, with loading from N calibration files.
17. **Buffer length.** The 1-second AI buffer in `_collect_finite_ai`
    is unchanged by adding channels (the `total_ms % 1000 == 0` rule has
    since been lifted; durations are trimmed to fit). Memory grows linearly
    with channel count (4 kS x 4 bytes x N_channels ~ tens of kB), well
    within budget.
18. **`AoDataGenerator`.** A profile must be generated per AO. All
    AO buffers must be the same length and use the same pacer; this
    is a constraint on how the program JSON is expanded.
19. **`apply_calibration` in
    [modes.py:180-270](../src/pioner/back/modes.py#L180-L270)** reads
    fixed AI column labels (`UTPL_AI`, `UMOD_AI`, `UHTR_AI`,
    `HEATER_CURRENT_AI`). It must be parameterized to accept an
    `area_id` and pick the correct columns and calibration entry.
20. **HDF5 layout.** Voltage profiles and AI frames are stored under
    fixed channel keys (`voltage_profiles/ch1` etc., see
    [../CLAUDE.md](../CLAUDE.md)). Group by `chip_id/area_id` instead
    of flat `chN`.
21. **Tango pipe / GUI.** Live traces must show per-area signals and,
    for differential operation, also S - R (and S/R, if useful).
    Decide which combinations are first-class in the UI.
22. **`mock_uldaq` backend.** Extend the mock to expose multiple
    "heater" channels with independent R_htr and thermal response so
    the test suite can run on a dual-area configuration without real
    hardware.
23. **Test suite.** Tests are written against a single channel.
    Either parameterize them across areas or duplicate the dual-area
    happy-path tests.

### 3.4 Calibration and operator procedure

24. **Per-area calibration polynomials.** Each area needs its own
    T(V_htr), AD595 correction (if a second AD595 is added), ihtr0,
    ihtr1, safe_voltage. The current single-file format will not
    suffice.
25. **Baseline runs.** The motivation for this work is to remove the
    empty-chip baseline run by using the on-chip reference. A
    procedure is still needed to validate that the reference area
    actually tracks the sample area's thermal response when both are
    empty, before any sample is loaded. Without that validation step
    the differential measurement has no audit trail.
26. **Martin calibration procedure.** The lab procedure document at
    [Martin-calibration-procedure.docx](Martin-calibration-procedure.docx)
    has not been parsed in this analysis. Before finalising the
    multi-area calibration flow, check whether it already prescribes
    a dual-area procedure that should be matched.

---

## 4. Open decisions needed before implementation

1. **Which of Option A, B, or C?** Or a combination. The choice
   drives both the front-end hardware and the scope of the firmware
   rework.
2. **Maximum number of simultaneous areas: 2, 3, or 4?** This
   determines whether the design hits the 4-AO ceiling.
3. **Is power-compensated operation a requirement, or is heat-flow
   (S - R) sufficient?** This is the watershed between Option A and
   Option B.
4. **Can AO ch2 (current trigger AO) be released?** Moving the
   trigger to DIO or to a counter line frees the fourth AO for
   Options B and C.
5. **Is the dual-area chip already chosen?** If a specific topology
   exists, its R_htr matching and thermal symmetry need to be
   measured before locking in the differential architecture.

---

## 5. DAQ envelope summary for planning

Per-area channel cost (Option A, B, or C):

| Quantity              | Per area | 2 areas | 4 areas |
|-----------------------|----------|---------|---------|
| AO drive              | 1 (A: 0.5 shared) | 1-2 | 2-4 |
| AO bias               | shared / hardware | -   | -   |
| AO trigger            | shared            | -   | -   |
| AI V_shunt            | 1        | 2       | 4       |
| AI Umod (high-gain)   | 1        | 2       | 4       |
| AI Utpl (standard)    | 1        | 2       | 4       |
| AI V_htr feedback     | 1        | 2       | 4       |
| AI AD595              | shared (1-2 total) | 1-2 | 1-2 |
| Total AO (worst case) | -        | 2-4     | 4       |
| Total AI (worst case) | -        | 9-10    | 17-18   |
| Aggregate AI rate @ 20 kHz | -   | ~200 kS/s | ~360 kS/s |

All numbers fit USB-2637 (64 AI, 1 MS/s aggregate). The 4-area case
saturates the AO bank.

---

## 6. Recommended next step

Pick one of A / B / C and commit to a maximum number of areas. Then
sequence the work in this order, smallest blast radius first:

1. Hardware front-end design (shunts, amplifiers, summing nodes,
   trigger relocation).
2. Calibration data model (multi-area `Calibration`, file format).
3. `channels.py` and `apply_calibration` parameterization.
4. JSON program schema (coordinated with the IR merge).
5. HDF5 layout, Tango pipe, GUI.
6. `mock_uldaq` extension and test suite parameterization.
7. Real-hardware validation: empty-chip S - R baseline before any
   sample is loaded.
