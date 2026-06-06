# PIONER — TODO / roadmap

Single forward-looking backlog for the whole project: back-end, front-end,
hardware bring-up, and cross-cutting work. Each item is self-contained: what to
do, where, why, and how to verify. **P0** items go first, **P3** is polish.
Current state (what already works) lives in [README.md](README.md); resolved
incidents live in [ERRORS.md](ERRORS.md) + `postmortem/`.

Sections below: **P0** critical correctness, **P1** architectural/feature work
(incl. hardware bring-up, front-end, closed-loop control, and the
open-source/proprietary split — see [pioner-pypi.md](pioner-pypi.md)), **P2**
code quality, **P3** docs.

File references use the `path/to/file.py:line` format. Test command:
`PYTHONPATH=src .venv/bin/pytest -q`.

## Status

- `pytest tests/`: **122 passed** (mock backend, ~30 s).
- `python -m pioner.back.debug` runs all three modes end-to-end clean.
- Mock-DAQ pipeline verification: see `docs/mock-verification.md` — modulation
  + lock-in confirmed within ~10 % of the analytical amplitude, no sample
  loss, `Uref` tiled correctly for finite / CONTINUOUS / DC-iso paths.
- All "won't run" bugs are closed; remaining work is architectural rough
  edges and physical fidelity items for real hardware.
- Pipeline reference: `docs/pipeline.md`. Manual mock usage: `docs/mock-verification.md`.

**Conventions kept on purpose:** column name `Uref` (not `Uheater`).
Heater channel `"ch1"` is now the named constant `HEATER_AO` in
`pioner.shared.channels` (see that module for the full layout); the wire
format remains `"ch{N}"`. (The `total_ms % 1000 == 0` whole-second constraint
has been lifted -- fractional-second durations are now allowed.)

---

## P0 — critical correctness bugs (open)

### P0-3. `apply_calibration`: Ihtr calibration is intentionally dimensionless

**Where:** `src/pioner/back/modes.py` (`apply_calibration`)

**Status (confirmed with physicist 2026-06-01):**
Production calibration files use `ihtr0 = 0, ihtr1 = 1`. This is intentional:
`ih = V_ch0` (volts, not amperes). AI ch0 is the node after the series resistor
before the amplifier loop — it is a voltage proportional to heater current, not
a shunt voltage with a known R_shunt. The `Thtr` polynomial is fitted against
this voltage-proxy directly, so `Rhtr = V_heater / ih` is dimensionless
(V/V), and the polynomial coefficients absorb the implicit scaling. The circuit
does NOT use a separate shunt resistor measurable by AI ch0. The comment in
modes.py claiming `ihtr1 = 1/R_shunt ≈ 5.88e-4` is wrong — it has been
corrected.

**Open (low priority):** a proper physical calibration in SI units (ih in
amperes, Rhtr in ohms) would require knowing the transfer function of the
amplifier loop on ch0. If that becomes available, add a note to the calibration
wizard and adjust the polynomial fitting accordingly.

### P0-4. IsoMode AO buffer is not seamless at the production f_mod = 37.5 Hz

**Where:** `src/pioner/back/modes.py` (`IsoMode._build_profiles`) and
`settings/settings.json` (default `Modulation.Frequency = 37.5`).

**What:** the iso AO buffer is sized to exactly 1 second (`n = sample_rate
= 20000`). With `f_mod = 37.5 Hz` that is `37.5` cycles in the buffer ->
the CONTINUOUS replay re-emits sample 0 with a phase offset of
`pi rad` (half a period), producing a square-wave-like edge at every
1 s wrap. In practice it is quasi-seamless (a few periods of glitch at
each wrap), not a hard discontinuity — confirmed with the physicist 2026-06-01.

`shared.modulation.check_ao_period_integrity` now logs a WARNING at
`IsoMode.arm()` quantifying the defect. The warning is the diagnostic;
the production fix is one of:

1. Drop `f_mod` to a value such that `n * f_mod / sample_rate` is an
   integer. At `fs = 20 kHz`, `n = 20000`, the eligible set is
   `f in {1, 2, 4, 5, 8, 10, 16, 20, 25, 40, 50, ...}` Hz. `40 Hz` is
   the closest to the historical 37.5 Hz; the C_p calibration may need
   to be re-checked.
2. Or size the AO buffer to the smallest integer-cycle multiple at
   37.5 Hz (= 1600 samples = 80 ms; LCM of 1600 and `n` ≤ rate is 19200
   samples = 0.96 s) by exposing the AO buffer length as a setting.

**Priority: low** (quasi-seamless is acceptable for current measurements).

**Physicist answer (2026-06-04):** keep `f_mod = 37.5 Hz` as-is for now. It is
changeable later, but the open question is *why exactly 37.5 Hz* historically
(provenance to be recovered). The one hard constraint when it is eventually
retuned: **avoid mains frequencies (50 / 60 Hz)** and their harmonics so the
lock-in does not sit on line pickup. No code change now; revisit when the
provenance is known and a bench re-check of C_p is scheduled.

### P0-5. AO/AI start skew — no trigger on rig; software offset-trim if needed

**Where:** `src/pioner/back/experiment_manager.py` (`finite_scan`),
`src/pioner/back/daq_device.py` (`DaqParams.hardware_trigger`,
`fire_software_trigger`).

**Status:** the trigger primitive is implemented and mock-tested (see
`tests/test_modes_e2e.py::test_fast_mode_with_hardware_trigger_runs_clean`).
Both AO and AI pre-arm with `ScanOption.EXTTRIGGER` when
`BackSettings.daq_params.hardware_trigger=True`, and a single
`fire_software_trigger` call releases them on a shared t=0. Default is
`False` so existing callers and mock tests are unaffected.

**Now config-driven (2026-06-03):** `hardware_trigger` is parsed from the
`HardwareTrigger` boolean in the `DAQ` block of `settings.json` /
`default_settings.json` (`HARDWARE_TRIGGER_FIELD` in `shared/constants.py`,
parsed in `BackSettings.parse_daq_params`). The loopback validation below can
now be turned on without a code edit — just flip `HardwareTrigger: true`.

**Confirmed with physicist 2026-06-01:** correct start order is AI first,
then AO — this matches the current code (`_start_ai_scan` is called before
`_start_ao_scan` in `finite_scan`).

**Physicist answer (2026-06-04):** the production rig has **no external
trigger line** (no DIO/jumper wired to the board trigger input). So the
`EXTTRIGGER` loopback below cannot be run as-is, and `HardwareTrigger` stays
`false` by default. If the residual AO/AI start skew turns out to matter, the
planned path is the **per-host software offset trim** (measure the persistent
skew once, store it, trim the leading N samples in `apply_calibration`) rather
than wiring a trigger.

**Note (arm/start workflow, 2026-06-05):** the absence of a hardware trigger
is what forces fast's AI-arm (begin acquisition) to live on **start**, not on
**arm**. Without a trigger an armed AI scan acquires immediately, so a human
pause between arm and start would fill fast's single-shot buffer with baseline
before the event fires. Today fast's **arm** therefore only reconfigures the AI
device to the fast rate (and pauses the live ring); **start** does AI-arm then
AO back-to-back (AI-first, ms apart). If a trigger line is ever added, AI can
prime-and-wait at **arm** and **start** just fires `fire_software_trigger`,
restoring the natural arm=prime / start=fire model and removing the leading-edge
latency window. See the P1-17 "Plan 2026-06-05" block for the arm/start design.

**Open:** if/when skew matters, implement the software offset-trim. (The
`EXTTRIGGER` loopback validation only applies if a trigger line is ever added.)
Drive a 1 kHz square wave on AO ch1, read it back on AI ch1, find the leading
edge; the fallback options are documented inline in `finite_scan`
(pacer-clock sharing or a per-host software offset trim).

---

## P1 — architectural / logical improvements

### P1-6. Tango: `select_mode` + `arm` state machine is not fail-loud

**Where:** `src/pioner/back/nanocontrol_tango.py:183-203`

**What:** `select_mode` stores `self._mode_name`. `arm(programs_json)`
reads it. If the user forgot `select_mode`, the previous value is reused
silently — surprising and easy to break in a multi-step session.

**Action:** introduce a single `arm(name, programs_json)` command that
takes the mode name explicitly. Keep `select_mode` + `arm(programs_json)`
as deprecated aliases that log a warning when used.

### P1-8. `start_ring_buffer` does not confirm the AI scan reached RUNNING

**Where:** `src/pioner/back/experiment_manager.py:240-254`

**What:** `ai_handler.scan(...)` returns the rate but does not assert that
the scan actually started. The worker thread immediately sees
`ScanStatus != RUNNING` and exits silently; `snapshot_ring_buffer()`
returns an empty array with no explanation.

**Action:** after `ai_handler.scan(...)`, poll up to ~100 ms for
`get_scan_status()[0] == RUNNING`. Raise `RuntimeError` on timeout.

### P1-11. `BackSettings.parse_*`: mixed validation styles (immediate vs deferred)

**Where:** `src/pioner/shared/settings.py:104-243`

**Action:** unify on batched collection (helper returns `(value, ok)`,
does not raise). The user gets all problems on one line instead of one at
a time.

### P1-12. `ScanDataGenerator` silently zero-fills missing channels

**Where:** `src/pioner/back/ao_data_generators.py:60-69`

**Action:** `logger.info("AO ch%d not provided, holding at 0 V", ch)`.

### P1-13. `_collect_finite_ai`: needlessly tight 1 ms busy-poll

**Where:** `src/pioner/back/experiment_manager.py:362`

**What:** the polling loop sleeps 1 ms between iterations and calls
`ai_handler.status()` on every wake. Half-buffer flip events occur **2×
per second** (1 s buffer, two halves), so ~99.8 % of the 1000 wakes per
second do nothing useful. On a desktop this is invisible; on a Raspberry
Pi each wake costs a syscall and a context switch — single-digit % CPU
wasted continuously, plus jitter for the ring-buffer thread. Not a
correctness bug.

**Action:** sleep `half_per_channel / sample_rate / 4` (≈ 125 ms at 20
kHz) — wakes 4× per flip, still safe. Same fix for `_ring_loop`.
Alternative: a driver-side event if `uldaq` exposes one (typically does
not in polling mode).

### P1-14. `mock_uldaq._fill_loop` is pure-Python and slow

**Where:** `src/pioner/back/mock_uldaq.py:320-353`

**What:** one `math.sin` call per sample. A 60-second scan at 20 kHz with
6 channels = 7.2 M iterations ⇒ ~3 s of CPU on the mock side, which
distorts the timing of long iso runs.

**Action:** generate `chunk_samples` with numpy in a single call
(`np.sin(omega * t_arr)` + broadcasting over channels). Slice-assign into
`buf[base:base+n_chans*chunk]`.

### P1-15. `mock_uldaq._synthesise_sample` injects a coherent ~196 Hz tone

**Where:** `src/pioner/back/mock_uldaq.py:362`

**What:** `math.sin(t * 1234.5 + channel) * 0.5e-3` is deterministic
(useful for tests) but it is also a **clean tone at ~196 Hz** with 0.5 mV
RMS. Visible in any FFT and lock-in at that frequency. Misleading when
debugging if `f_mod` is anywhere near 196 Hz.

**Action:** replace with `np.random.default_rng(seed=hash(channel))`
Gaussian noise of the same RMS. Make the seed configurable via
`PIONER_MOCK_NOISE_SEED`.

### P1-16. `Calibration.read` produces unfriendly errors on malformed files

**Where:** `src/pioner/shared/calibration.py:177-209`

**What:** direct indexing like `coeffs[U_TPL_FIELD]["0"]` raises bare
`KeyError` with no context.

**Action:** wrap the field-extraction block in
`try/except KeyError as exc: raise ValueError(f"Missing field {exc} in
calibration file {path}")`.

### P1-17. Live AI streaming architecture (persistent AI + dormant disk recorder)

**What:** SlowMode / IsoMode / Calibration currently block until the run
finishes. Operator wants real-time UI updates plus chip-alive monitoring
between experiments. Full design + decision log captured in
[docs/live-streaming.md](docs/live-streaming.md).

**Action:** Implement persistent AI scan (`Connect` -> `Disconnect`),
ring buffer with `peek` / `read_new(consumer_id)`, dormant `DiskRecorder`
(open at Arm, close at experiment end), `MonitorAO` helper for
between-experiment AC drive. Sliding-window FFT demod for UI display.
~3-4 days back-end, ~1 week UI, ~1 week hardware soak. Six open
questions in §11 of the design doc need answers before code lands.

**Status (partial, done):** Persistent + per-experiment `AIProvider`
(`back/acquisition/`), ring buffer `peek_last`/`read_new`, `AcquisitionMode`
config flag, `DeviceController` adapter (`back/device_controller.py`,
`LocalDeviceController` runs experiments on mock/real DAQ without Tango),
single-window live streaming inside `mainWindow` (Signals tab scope +
Values readout via `calibrate_window`), CLI `runUI --mock/--hardware`.
The standalone `streamWindow`/`runStream` dev window was folded into
`mainWindow` and removed.

**Status (iso live -- done, 2026-06-01):** `IsoMode.run()` takes an
optional injected `ExperimentManager` + `snapshot` callable. The finite/timed
iso path (`LocalDeviceController._run_iso_streaming`) drives only AO on the
controller's manager and reads AI from the persistent ring (primed
`read_new` cursor -> captures just the run window), stopping only AO
afterwards. The default GUI "Set" now uses the non-blocking eternal hold
(`start_iso_hold` -> `IsoMode.start_hold`, P1-5), same drive-only-AO principle.
The live stream stays active for the whole iso run.
Mode-selection UI (Fast/Slow/Iso combo) wired in `mainWindow`. Regression
tests `test_iso_run_keeps_stream_live` / `test_iso_run_streams_during_run`.

**Status (still open):** (a) **Fast / slow** modes still arm their own
finite AI scan, so `LocalDeviceController.run()` **pauses** the live stream
for the duration of a fast/slow run (resumes after). Lifting this needs
FastHeat/SlowMode to read the shared ring like iso now does, plus
real-hardware sample-alignment validation at >1000 K/s (mock cannot verify
it). (b) `DiskRecorder` (record-from-Arm) not built. (c) `MonitorAO`
between-experiment drive not built. (d) Tango path is incompatible with
persistent AI and is currently
disabled (`nanocontrol_tango.py` raises); `TangoDeviceController` exists
but is unverified -- repair when Tango becomes relevant again.
(e) Live `Thtr`/`Rhtr` show the ~-1071 sentinel at idle (no heater
current) because the NaN-at-zero-current threshold (1e-9 A) is below mock
noise; suppress R/T readout when no AO drive is active, or raise the
threshold. See P0-3.

**Plan (2026-06-05): unified arm/start/stop workflow + record-from-arm.**
Design agreed with the operator. Reframes live streaming as the *default device
state* (not a mode) and gives every experiment a three-button lifecycle.

*Mental model.* A single persistent AI provider (the ring) runs from Connect to
Disconnect. The "default state" is a room-temperature / zero isotherm: watch the
modulated ch0 signal and optionally set the (infinite) hold temperature. There
is exactly **one AI scan on the USB-2637 at a time** -- that hardware fact is
why iso/slow read from the ring while fast must own a separate scan.

*Three-button lifecycle (all modes).* `arm` = "signals OK, prepare / start
recording baseline"; `start` = "launch the experiment"; `stop` = "abort, zero
the heater, finalise the save". Button gating: `start` disabled until `arm`,
`stop` disabled until `start`, `arm` disabled until `Apply` (the per-mode rate
+ Apply gate landed 2026-06-05) and until a chip is detected (P1-36).

*Per mode (rate from the per-mode map in settings; landed 2026-06-05):*
- **fast** (20 kHz, own single-shot DEFAULTIO scan): `arm` = pause ring +
  reconfigure AI to 20 kHz (configure only, NOT acquiring -- live plot freezes
  during the arm->start wait, accepted). `start` = AI-arm then AO back-to-back
  (AI-first, P0-5) in a tight critical section -> read once -> resume ring at
  2 kHz. No baseline (set by hand in the temperature program). AI-arm sits on
  `start` (not `arm`) precisely because there is no trigger -- see P0-5 note.
  Jitter minimisation: tight back-to-back issue + post-hoc leading-edge
  detection (the rise is in the captured baseline). Fast `stop` is low value
  (sub-second) but must still zero AO cleanly; **fast zeroing is optional for
  now (operator)**.
- **slow** (2 kHz == monitor rate, reads from persistent ring, **no pause** --
  this is the long-deferred "Approach A"): `arm` = start the DiskRecorder
  (baseline begins from the live ring, plot uninterrupted). `start` = launch the
  ramp + set the start-cursor (the ring read-index marking ramp t=0). Dataset =
  `[baseline][ramp]`. `stop` must be available and zero the heater. AO/AI
  alignment is by the software start-cursor (jitter is negligible for a slow
  ramp; measure residual skew on HW, P0-5). Overrun: 2 kHz CONTINUOUS has ~10x
  more drain margin than the 20 kHz that triggered the OVERRUN postmortem, but
  **soak-test on real hardware for full slow-ramp durations** (mock cannot
  prove it).
- **iso -- two paths**, selected by whether the duration field is set:
  - *Eternal hold* (duration empty, exists today): `start_iso_hold` drives AO
    DC+AC, live from ring, **no recording**, `stop` -> `zero_ao`.
  - *Finite iso experiment* (duration set, NEW): `arm` = start DiskRecorder
    (baseline); `start` = mark cursor + drive AO to the target **T > room temp
    (heating-only, no cryostat yet)** + AC; auto-stop after `total_ms`; finalise
    -> save h5. `stop` aborts early -> `zero_ao` + save partial (marked
    aborted).

*DiskRecorder (P1-17 item b, now needed -- gating dependency).* A ring consumer
that records from `arm`. `start(provider)` at arm: `reset_ring_cursor` -> open
h5 (append) -> background drain loop appends raw AI via `read_new`.
`mark_start()` at start: store the current sample index as experiment t=0.
`stop()` at end/stop: final drain, flush, close, then `apply_calibration`
(using the AO program offset by the cursor) and `save_run_to_h5`. Record **raw
AI**, calibrate at finalise. Works for slow and finite-iso (both ring
consumers); fast does not use it (single-shot, no baseline -- keeps its
end-of-scan `save_run_to_h5`). Drain frequently to stay ahead of overrun.

*Interruptible run + Stop button (P1-17 follow-on).* Today `run()` blocks, so
only an iso hold is stoppable. To make `stop` work for slow/fast the collect
loops (`_collect_finite_ai`, `_collect_finite_ai_single_shot`) must poll a
cancel flag; `stop` then `scan_stop`s AO+AI, calls `zero_ao()`, and finalises
the DiskRecorder (partial save marked aborted).

*Temperature limits (config, no cryostat yet).* Add `min`/`max` experiment
temperature to settings (decided: **min 0 C, max 300 C**, heating-only). Reject
programs / iso targets outside `[min, max]` at validation; this is in addition
to the existing `safe_voltage` clamp.

*Implementation order:* (1) per-mode rate + Apply gate -- **DONE 2026-06-05**
(in settings/controller/GUI; see README invariants); (2) DiskRecorder;
(3) slow off-ring (needs 2 + cursor); (4) iso two paths; (5) interruptible
run + Stop for all + temp limits + chip-detect gate (P1-36).

### P1-18. External trigger integration (synchrotron / Raman / diffractometer)

**What:** Multi-instrument workflow — chip sits in beam path, beamline
fires TTLTRG, PIONER captures synchronized response. Pre-trigger
baseline needed (no missed initial samples, no 500 ms gap on 1-second
fast-heat experiments).

**Action:** AO armed with `ScanOption.EXTTRIGGER`, AI persistent
(see P1-17). DiskRecorder active from Arm onward — pre-trigger baseline
captured naturally (= operator-controlled time between Arm press and
trigger fire). UI emits DIO "Ready" signal to beamline. Sample-accurate
trigger timestamping via counter input deferred until first synchrotron
run requires it. See §5 of [docs/live-streaming.md](docs/live-streaming.md).

### P1-19. Flash-chip support: additional AI channel for on-chip thermistor (Tamb)

**What:** Flash-chip variants have an on-chip thermistor wired in for
ambient-temperature sensing. Current AI channel map (6 channels:
Uref / Umod / Uhtr / Uaux / Utpl / Uhtrabs) doesn't expose this.

**Action:** Confirm pin allocation with operator. Extend
`DEFAULT_AI_CHANNELS` in `shared/channels.py`, settings schema,
`apply_calibration` to produce a `Tamb` engineering column.
Config-driven so existing 6-channel setups don't break. **TODO:** clarify
whether thermistor reads via the same Uaux/AD595 pipeline or a separate
channel.

### P1-20. Sample rate ceiling and per-segment dynamic rate

**What:** Operator has run experiments at 166 kHz stably but considers
that excessive. Suggested production ceiling: **50 kHz**. Higher rates
inflate file size linearly (50 kHz x 6 ch x 8 B = 2.4 MB/s sustained
vs current ~1 MB/s at 20 kHz). Idea: dynamic per-segment rate (fine
resolution during transient, coarse during isothermal hold) to keep
files manageable.

**Action:** (a) Document a hard sample-rate ceiling — default suggestion
50 kHz, capped in settings validator. (b) Investigate dynamic
per-segment rate. **Constraint:** mid-experiment rate reconfigure
breaks the persistent-AI assumption from P1-17. Alternatives: post-run
downsampling per region, or per-segment AO programs that the recorder
metadata-tags. **Open design question, requires operator + physics
discussion.**

### P1-21. Differential calorimetry (two chips or one chip with two regions)

**What:** Standard nanocalorimetry technique: compare sample-loaded chip
against reference chip to suppress common-mode drift. Either two
physical chips on one board, or one chip with two heater regions.
Not supported in current code.

**Action:** Hardware decision first — USB-2637 has 4 AO and 64 AI SE
channels, can drive two chips on one board. Need: extension of
`ChannelProgram` to per-chip programs, differential demod step in
`apply_calibration`, UI panel for two-chip setup, possibly new mode
`DifferentialMode` orchestrating both chips' AO programs simultaneously.
**Significant scope** — multi-week feature.

### P1-22. CalibrationMode per Martin algorithm

**What:** Mainline has no calibration workflow (JSON edited manually).
Operator wants this implemented per the Martin calibration procedure
(see [docs/Martin-calibration-procedure.md](docs/Martin-calibration-procedure.md))
with optimization of the polynomial fit stages.

**Action:** Port IR-branch's `CalibrationWizard`
([pioner-IR-branch/pioner_app/ui/calibration_wizard.py](pioner-IR-branch/pioner_app/ui/calibration_wizard.py))
as the UI scaffold. Adapt the three-stage flow (Thtr / Theater / Ttpl)
to the Martin algorithm specifics. Consider numerical-optimization
improvements (constrained least squares vs unconstrained, robust fit
against melting-plateau outliers). **Depends on P1-17** (live streaming
required for the cursor-pick during ramp). See also B1-B4 in
[docs/ir-merge-answers.md](docs/ir-merge-answers.md) for
procedure details (answers received from the IR-branch dev).

### P1-23. Thermostat / atmosphere control (cryogenic + gas-controlled experiments)

**What:** Open-air room-temperature experiments are limiting. To extend
to cryogenic ranges or controlled atmospheres, PIONER would need to
integrate with an intercooler / refrigerator / gas-flow system with
PID feedback. Closes the chamber → enables far more experiment types
(low-T phase transitions, oxidation-sensitive samples, etc.).

**Action:** Survey candidate hardware (Eurotherm, Lakeshore, etc.) —
choice TBD by operator. Design as a separate hardware abstraction
layer (parallel to DAQ). Add T_ambient / setpoint / flow signals,
PID command path, safety interlocks for chamber sealed-state.
**Significant scope** — multi-month feature, not a fix.

### P1-24. Closed-loop (feedback) temperature control

**Priority: medium.** **Where:** new control layer over
`back/experiment_manager.py` / `back/modes.py`; iso is the easiest first test
bed (single setpoint), but the loop is mode-agnostic.

**What:** today every mode is open-loop: a commanded voltage profile is played
out on AO and the resulting temperature is only *measured*, never *corrected*.
Add a closed-loop controller that adjusts the drive in real time so the chip
tracks a temperature setpoint (and, importantly, does not overshoot/overheat).

- **Controller:** PID in the Laplace (s-domain) formulation. The derivative
  term is what bounds overshoot and protects the chip from overheating; tune
  for the chip's fast thermal time constant. (User note said "Laplacian" —
  read as the s-domain transfer-function / derivative term; confirm the exact
  formulation with the physicist before implementing.)
- **Actuator:** `Uref` is the direct drive signal we already command, so it is
  the natural control handle — the loop modulates `Uref` (within the
  `safe_voltage` clamp) instead of replaying a fixed profile.
- **Measured variable / error:** `temp-hr` (the high-rate temperature and its
  change over time) feeds the negative-feedback path; error = setpoint - temp.
- **Prior art:** the legacy Bondar / uCal implementation did **not** account
  for feedback properly — do not port it verbatim; treat as a clean design.
- **Advanced option (research / open question):** state-space ("state-matrix")
  modelling and modern control theory (e.g. LQR / model-based) instead of a
  hand-tuned PID, possibly tied into the calibration. Investigate feasibility
  and whether it buys accuracy over PID. Flagged as a research spike.
- **Reuse:** the same PID path serves the cryothermostat / atmosphere control
  loop (see P1-23).

**Verification (mock first):** drive a step setpoint on the mock, confirm the
loop settles without sustained overshoot; only then tune on real hardware
(HARD STOP — overshoot melts the heater, see the `safe_voltage` rules in
CLAUDE.md). The iso "hold" path (start_iso_hold) is in place to build on.

### P1-25. Replace AD595 cold-junction with a K-type thermocouple converter

**Priority: medium** (accuracy + cost). **Where:** AI ch3 / `Taux` path in
`back/modes.apply_calibration` and `hardware.correct_ad595`;
`shared/channels.py`.

**What:** the AD595 (cold-junction-compensated op-amp on ch3, scaled
100 C/V) is an expensive part of limited value, and its whole-scan averaging
already costs accuracy on slow ramps (~0.5 C drift, see CLAUDE.md and
P2-21 / Martin-calibration-procedure.md). Plan to replace it:

- Read a **type-K (chromel-alumel) thermocouple** through a
  **MAX6675 Cold-Junction-Compensated K-Thermocouple-to-Digital Converter**
  (0 C to +1024 C) instead of the AD595 analog channel.
- **Remove the `Taux` AI channel (ch3)** from the analog pipeline once the
  thermocouple path is in; **repurpose ch3** for chips that carry an on-chip
  **thermoresistor** (ties into P1-19's thermistor / Tamb channel).

**Open / verify before ordering:** MAX6675 is an **SPI digital** device, not
an analog voltage source — it does **not** read on a USB-2637 AI channel
directly and needs an SPI interface (microcontroller / adapter), which is an
acquisition-path change, not just a calibration tweak. Also confirm its
range / resolution (~0.25 C, 12-bit) fit the experiments and whether its
newer successor (MAX31855) is a better choice. Decision pending with the
physicist / EE.

### P1-26. Split codebase: open-source core library vs. proprietary nanocal code

**Priority: high.** **Where:** repo-wide (cross-cutting; tracked here per
request even though it is not back-end-only).

**What:** investigate whether the code can be cleanly separated into
(1) a **general open-source library** — the reusable, instrument-agnostic
parts (DAQ abstraction + mock backend, software lock-in / demodulation, the
calibration framework, settings plumbing) — and (2) **proprietary code
specific to the PIONER nanocalorimeter** (chip calibration coefficients and
fits, the chip-specific modes, heater/guard topology, safety limits).

**Action:** map every module to "generic" vs "nanocal-specific", identify the
API boundary and any leaks across it, decide packaging (two distributions vs
a plugin/extras split) and licensing for each side. Output a short proposal
before any code move. **No code change until the boundary is agreed.**

### P1-27. SPICE digital twin of the analog front-end / board

**Where:** documentation + EDA tooling (cross-cutting; not back-end code).

**What:** build a SPICE model of the board / analog front-end as a digital
twin (per-component SPICE models of each element of the system/board), so the
amplifier loop, the heater-current proxy on ch0, and the thermocouple /
thermistor path can be understood and simulated rather than reasoned about
from the schematic by hand.

**Action / references to evaluate:**
- SPICE component libraries: <https://youspice.com/spice-libraries/>
- Background article: <https://habr.com/ru/articles/948954/>
- Altium Designer (eCAD) ships simulation modules with a SPICE model per
  element — evaluate using it to navigate and simulate the schematics.

Goal: a maintained schematic + SPICE model that documents the real signal
chain (feeds back into P0-3 calibration provenance and P1-25 front-end
changes). Investigation first; deliverable is a model + short notes, not code.

### P1-28. Hardware bring-up on a real USB-2637

**Where:** operator checklist in [docs/hardware-bringup.md](docs/hardware-bringup.md).

**What:** the code preparation for hardware-mode testing has landed (real-vs-mock
status readout, settings-driven `HardwareTrigger`, connect diagnostics, idle-Thtr
guard, sample-count logging). The remaining work needs the physical board and is a
**HARD STOP** per `CLAUDE.md`. Ordered bring-up steps:

1. Install `libuldaq` + `.[hardware]`; confirm the GUI status reads
   `REAL DAQ (uldaq)` and idle Thtr shows `---`.
2. Short fast / slow / iso runs cross-checked against
   [docs/mock-verification.md](docs/mock-verification.md) tolerances; confirm the
   `AI finite scan complete: N / N` log (no short frame).
3. P0-5 skew check (see P0-5): no trigger line on the rig, so measure the residual
   AO/AI skew and, if it matters, implement the per-host software offset-trim.
4. Then the live-chip accuracy items that cannot be pre-validated on the mock:
   P0-4 iso seamlessness at 37.5 Hz, lock-in edge transients (now flagged by
   the `temp-hr_valid` mask), fast/slow
   live-stream-during-run (P1-17 Approach A, alignment > 1000 K/s).

### P1-29. Front-end: offscreen GUI regression tests

**(front-end).** **Where:** `src/pioner/front/mainWindow.py`,
`src/pioner/front/mainWindowUi.py`, new `tests/test_main_window.py`.

**What:** several GUI behaviours are only exercised by an ad-hoc offscreen
smoke, not by the suite. Add `QT_QPA_PLATFORM=offscreen` regression tests so
they cannot silently regress:
- connect status readout (A1) MOCK vs REAL, connect diagnostics (A2), idle-Thtr
  blanking (A3);
- iso eternal hold vs timed program (the duration field): Set holds and the
  live Thtr shows; Off / timer expiry drives 0 V and blanks Thtr.

(The iso hold/timed UI itself has landed: `setDurationInput` + `start_iso_hold`
+ the auto-Off `QTimer`; this item is now only about test coverage.)

### P1-30. Quantify / harden the mainline `finite_scan` OVERRUN margin

**Where:** `src/pioner/back/experiment_manager.py` (`_collect_finite_ai`,
`_ring_loop`). Background: the FIFO-overrun incident,
[postmortem/2026-05-23-fifo-overrun-continuous-ai.md](postmortem/2026-05-23-fifo-overrun-continuous-ai.md).

**Done for fast-heat:** `finite_scan(single_shot=True)` now arms AI as
`DEFAULTIO` with a host buffer sized to the whole scan and reads it once at IDLE
(`_collect_finite_ai_single_shot`); `FastHeat.run` uses it. No half-buffer drain
race -> the fast-heat OVERRUN class is removed (the IR-branch fix). Verified on
mock for whole + fractional seconds.

**Still open:**
- **Slow-heat + live streaming stay on the `CONTINUOUS` one-second half-flip
  path** (`_collect_finite_ai` / `_ring_loop`) -- same risk class at 20 kHz x 6
  ch. Decide whether to move slow to single-shot too, or document a sample-rate
  ceiling for the streaming paths.
- **Hardware validation:** the mock cannot reproduce `ULError.OVERRUN`, so the
  fast-heat fix and the slow/live margin must be confirmed on the real board
  (20 kHz x 6 ch x 3 s, bare metal and VM). The B3 sample-count logging
  (`AI finite scan short ...` WARNING) surfaces a short frame at runtime.
- Investigate whether `DEFAULTIO` issues larger DMA transfers than `CONTINUOUS`
  (would further raise the effective drain rate). Not yet verified.

### P1-32. Apply AC amplitude correction (`ac0..ac3`) -- from Bondar uCal

**Priority: high.** **Where:** `shared/calibration.py` (`ac0..ac3` exist),
`back/modes.py` (lock-in amplitude in `SlowMode`/`IsoMode.run`).

**What:** the amplitude-correction polynomial `kamp(T) = ac0 + ac1*T + ac2*T^2
+ ac3*T^3` is loaded, saved and shown in the GUI, but **never applied at
runtime** -- the demodulated lock-in amplitude is not divided by it. Bondar
divides the AC amplitude by this temperature-dependent factor before reporting
(Bondar-uCal.md §10.3 / Unit4.cpp:3414-3644). If the thermopile gain varies
with T, our C_p is biased. Apply `amplitude /= kamp(temp)` after demod.

**Verification:** unit test that a non-identity `ac*` scales the reported
amplitude as expected; identity (`ac1=1`, others 0) leaves it unchanged.

### P1-33. In-situ R-correction auto-zero (`Rhcorr` / `Rhdcorr`) -- from Bondar uCal

**Priority: high.** **Where:** `shared/calibration.py` (`thtrcorr` /
`thtrdcorr` fields exist), new operator action.

**What:** Bondar runs a damped Newton iteration (gain 0.1, tol 0.01 C, up to
1000 steps) that trims the heater-resistance correction so `Thtr` agrees with
`Ttpl + Taux` at the current operating point (Bondar-uCal.md §4.3 /
Unit1.cpp:1308-1342). PIONER has the `thtrcorr`/`thtrdcorr` fields but no way
to compute/update them in the field. Port as `Calibration.compute_rhcorr(...)`
so daily drift is corrected without re-fitting the whole Thtr polynomial.

### P1-34. Lock-in reference = measured heater current (AI ch0) -- from Bondar uCal

**Priority: high (needs bench confirmation).** **Where:**
`shared/modulation.py` (`lockin_demodulate` uses a synthetic `sin(omega*t)`),
`back/modes.py` (never passes AI ch0 to the lock-in).

**What:** Bondar correlates the signal against the **measured** shunt/current
reference (AI ch0), not the commanded sine (Bondar-uCal.md §6 / Unit1.cpp:
721-963). At higher `f_mod` the real heater current lags the AO command, so the
measured reference puts the phase zero on the actual driving force. Add an
optional `reference: np.ndarray | None` to `lockin_demodulate`; when given, use
it instead of the synthetic sine. Confirm the phase-lag magnitude on the bench
before making it the default.

### P1-35. Experiment presets (`experiment-config/` TOML)

**Priority: medium.** **Where:** new `experiment-config/` folder, `front/`
(combo-box loader), `shared/` (preset parser).

**What:** let users save reusable experiment presets as commented TOML files in
`experiment-config/`, each holding a preset name, mode (`fast`/`slow`/`iso`),
temperature program (and/or iso target + duration), sample rate override, and
free-text comments documenting the experiment. The GUI gains a preset combo-box
that loads the selected file into the program/mode/rate fields. **Default
selection is empty** (no preset) so nothing is auto-applied.

**Why TOML:** human-editable, comments are first-class (unlike JSON), maps
cleanly to the program-table + metadata shape. Keep the existing `settings.json`
as-is; presets are a separate, optional input layer.

**Action:** define the preset schema (name, mode, program table, rate, notes);
parser with clear errors on malformed files; UI combo lists `experiment-config/
*.toml` by `name`; selecting one populates fields (still requires `Apply` ->
`arm`; the Apply gate). Ship 1-2 example presets with comments.

### P1-36. Chip-presence detection -- gate arm/start/stop

**Priority: high (safety).** **Where:** `back/experiment_manager.py` /
`back/device_controller.py`, `front/` (button gating). **Related:** P2-24
(heater broken/shorted thresholds) -- same primitive.

**What:** there is no point driving voltage if no chip is connected. Detect
presence programmatically and **disable arm/start/stop when absent**.

**Approach (UNVERIFIED -- needs bench/physicist confirmation):** continuity
probe -- drive a small safe voltage on the heater (AO ch1) and watch the
**heater-current proxy on AI ch0**. NOTE: AI ch0 is a *voltage proxy* for heater
current, **not a calibrated shunt** (`channels.py`; `modes.py:261` says
explicitly "NOT a shunt voltage with a known R_shunt") -- the shunt-path *bias*
is on AO ch0. So this can only be a **presence/continuity** test (does current
flow at all when probed), not a precise resistance reading: open circuit
(proxy ~ 0, no current) => no chip / broken heater; clear current response =>
present. The heater-voltage feedback on AI ch5 (`UHTR_AI`) can cross-check.
Same family as Bondar's broken/shorted-heater thresholds (P2-24). **Unknowns to
confirm before coding:** whether a dedicated presence pin exists, the exact
wiring, and the proxy threshold. Do not implement the threshold from a guess.

**Action (after confirmation):** `DeviceController.chip_present() -> bool`
(probe + threshold); poll it for the button-enable state; re-check at `arm`.

### P1-37. Minimise fast-heat start jitter (no trigger on rig)

**Priority: medium.** **Where:** `back/experiment_manager.py` (`finite_scan`
single-shot path), `back/modes.py` (`FastHeat`). **Related:** P0-5 (skew),
P1-17 plan.

**What:** without a hardware trigger the AI-arm -> AO-start gap has variable
latency (jitter), skewing the captured leading edge of the ballistic event.
Two practical mitigations (the real cure -- a trigger line -- is deferred,
P0-5/P1-18):
1. **Tight critical section:** issue AI-arm then AO-start back-to-back with no
   logging / allocation / GC between them, on one thread. Shrinks the mean gap
   and its variance.
2. **Post-hoc edge detection:** fast captures leading baseline, so the rise is
   in the data -- align the analysis to the detected edge instead of commanded
   t=0. Removes jitter's effect on alignment entirely (robust fix).

**Verification:** on real HW, measure the spread of the detected edge position
across repeated identical fast runs before/after; mock cannot reproduce the
jitter.

---

## P2 — code quality / DX

### P2-2. Typo: "(former Nanocal)" → "(formerly Nanocal)"

**Where:** `pyproject.toml:11`, possibly `README.md`.

### P2-3. `pyproject.toml`: add a console_script for the Tango server

**Action:** `pioner-tango = "pioner.back.nanocontrol_tango:NanoControl.run_server"`.

### P2-4. Single logging configuration entry point

**Action:** `pioner/logging_setup.py` exposing `configure(level=INFO,
file=None)`. Call it from CLI / Tango entry points.

### P2-5. Inconsistent type-hint style

**Action:** `ruff format` plus an explicit style guide. PEP 604
(`X | None`) plus `from __future__ import annotations` everywhere.

### P2-6. `BackSettings.get_str` builds JSON via `dict→str→replace`

**Action:** `json.dumps({"DAQ": vars(self.daq_params), …})`.

### P2-7. `is_int_or_raise` name does not match behaviour

**Action:** rename to `validate_int(value, *, name="value")`. Keep the
old name as an alias for one release.

### P2-8. Duplicated HDF5 saving in legacy facades

**Where:** `src/pioner/back/fastheat.py:86-107`,
`src/pioner/back/slow_mode.py:65-95`.

**Action:** extract to `pioner.back.hdf5_export.save_experiment(...)`.

### P2-10. Remove or implement `FAST_HEAT_CUSTOM_FLAG`

**Where:** `src/pioner/back/fastheat.py:55-68`

**What:** the parameter is accepted, stored, but never read anywhere.

### P2-11. `AiDeviceHandler` test coverage

**Action:** add `tests/test_ai_device.py`:
- Buffer re-allocation on `samples_per_channel` change.
- `scan()` without `allocate_buffer` raises `ValueError`.
- Hard `RuntimeError` when the AI device reports zero SINGLE_ENDED
  channels (the device raises instead of silently falling back to
  DIFFERENTIAL; see `ai_device.py:73`).

### P2-12. Legacy `fastheat.FastHeat` / `slow_mode.SlowMode` have no tests

**Action:** `tests/test_legacy_facades.py` — run fast/slow through the
legacy classes, confirm the HDF5 file is created with the expected
structure.

### P2-13. Direct unit test for the half-buffer flip

**Action:** drive `_collect_finite_ai` against the mock with a
deterministic ramp `0..N`. After 5 s, assert all `N × 5` samples are
present, no duplicates, no gaps.

### P2-14. `Calibration.get_str` round-trip test

**Action:** `Calibration.get_str → json.loads → check field equality`.

### P2-15. `tests/conftest.py`: drop the `sys.path` hack

**Where:** `tests/conftest.py:11-12`

**What:** duplicates `pyproject.toml [tool.pytest.ini_options].pythonpath
= ["src"]`.

### P2-16. `parse_modulation` has a function-local `import`

**Where:** `src/pioner/shared/settings.py:114`

**Action:** move `from pioner.shared.modulation import ModulationParams`
to the top of the file.

### P2-17. `IsoMode._build_profiles` returns a 1-sample profile when AC is off

**Where:** `src/pioner/back/modes.py:472-476`

**What:** `{ch: np.array([prog.values[0]])}` — a single sample. Any code
that reads `voltage_profiles` without knowing about DC iso will be
surprised. (FIX A made `apply_calibration` tile this correctly, but the
data type asymmetry remains.)

**Action:** either return a full `n = sample_rate` line, or do **not**
return a profile at all for DC-only (separate `_dc_voltages: Dict[str,
float]`, checked in `run()`).

### P2-18. `ChannelProgram` does not catch NaN/Inf

**Where:** `src/pioner/back/modes.py:79-94`

**Action:** `if not np.all(np.isfinite(values)): raise ValueError(
"program values contain NaN/Inf")`.

### P2-19. `temperature_to_voltage` rounds to 4 decimals → 0.1 mV

**Where:** `src/pioner/shared/utils.py:118`

**What:** `np.round(volt_calib[idx], 4)`. The 16-bit DAC at ±10 V has an
LSB of ~0.305 mV; rounding to 0.1 mV is below the DAC resolution and just
quantises early.

**Action:** drop `np.round` (the DAC quantises by itself) or expose the
resolution as a parameter.

### P2-20. Port simpleFastHeatWidget segmentation feature from IR-branch

**What:** IR-branch's
[pioner_app/ui/widgets/simpleProcessWidget.py](pioner-IR-branch/pioner_app/ui/widgets/simpleProcessWidget.py)
lets the operator segment a recorded experiment (full trace / heating /
cooling / isotherm) and display only the segments of interest for
fit / inspection. Useful workflow that mainline doesn't have.

**Action:** Port the segmentation UI to mainline's `resultsDataWidget`
(or a new dedicated widget). ~600 lines from IR-branch, mostly
self-contained (silx + numpy + h5py only). ASCII cleanup needed.

### P2-21. Physical Ihtr calibration in SI units (low priority)

**What:** current production calibration uses `ihtr0=0, ihtr1=1`, so
`ih = V_ch0` (volts, not amperes) and `Rhtr` is dimensionless V/V. The
`Thtr` polynomial is fitted against this proxy directly. To calibrate in
proper SI units (ih in amperes, Rhtr in ohms), the transfer function of
the amplifier loop on AI ch0 must be measured. Low priority — the
proxy-based calibration works for relative temperature measurements.

**Interim guard:** `tests/test_calibration.py::test_default_calibration_pins_identity_constants`
pins `ihtr0/ihtr1/uhtr0/uhtr1` and the Thtr/Theater/amplitude polynomials to
their identity values, so they cannot silently drift before this SI
recalibration procedure is defined. When P2-21 lands, update that test with
the new measured coefficients in the same commit.

`tests/test_apply_calibration.py::test_rhtr_units_are_ohms_with_si_calibration`
already exercises the *hypothetical* SI path (`ihtr1 = 1/R_shunt`, `Rhtr` in
ohms); it documents the target arithmetic and can become the production unit
check once real coefficients are measured. **This is the low-priority "revisit
the heater-current calibration" task** (raised 2026-06-06).

### P2-22. Progress bar for slow/iso experiments (low priority)

**Where:** `src/pioner/front/mainWindow.py`

**What:** slow and iso scans run for tens of seconds with no UI feedback.
Add an artificial progress bar driven by elapsed time vs expected
`total_ms` from the armed program. Can be a `QProgressBar` updated by a
`QTimer` in `run_mode()`.

### P2-23. IR-drop-corrected heater voltage `Uhtr_eff` -- from Bondar uCal

**What:** Bondar shows the voltage across the heater itself, not the raw ch5
feedback, by subtracting the shunt IR drop: `Uhtr_eff = AI5 - AI0`
(Bondar-uCal.md §10.9 / Unit1.cpp:1172-1183, per-buffer mean). PIONER computes
both raw channels in `apply_calibration` but never derives this. Add a
per-sample derived column `Uhtr_eff`. Cosmetic/diagnostic, not physics.

### P2-24. Configurable heater broken/shorted thresholds + verify safe_voltage -- from Bondar uCal

**What:** Bondar flags `R > 9000 Ohm` -> "broken", `R < 50 Ohm` -> "shorted"
(hardcoded, Bondar-uCal.md §9.12) and ships `heatersafeV = 5.61 V` vs PIONER's
`safe_voltage = 9.0 V` (Bondar-uCal.md §4.1). Two actions: (1) add optional
`r_heater_broken_ohms` / `r_heater_shorted_ohms` to `Calibration` for a
fail-loud diagnostic; (2) **verify the 5.61 V vs 9.0 V discrepancy with the
physicist/EE** before the first real run (chip/era difference, or a stale
value). Diagnostic only -- low urgency for code, but the safe_voltage check is
a bring-up prerequisite.

### P2-25. Median + symmetric moving-average post-filter helpers -- from Bondar uCal

**What:** Bondar's `filter_it` offers a median smoother + symmetric IIR moving
average for denoising amplitude/phase/temperature traces (Bondar-uCal.md §10.6
/ Unit4.cpp:2672-2723). PIONER leaves all post-filtering to downstream
scipy/pandas. Add `shared/filters.py` (`median_filter`, `symmetric_ma`) as
opt-in post-processing for the result frame / HDF5 export.

### P2-26. Fast-heat exponential-fit deconvolution (`removexep`) -- from Bondar uCal

**What:** Bondar fits a bi-exponential rise+fall around the heater pulse and
subtracts it to recover the small calorimetric signal underneath (Bondar-uCal.md
§10.7 / Unit4.cpp:3085-3121). Useful for extracting heat capacity from noisy
fast-heat traces. Port as an optional analysis helper (`scipy.optimize`).
Advanced/expert feature.

### P2-27. In-situ phase zeroing (`addphase`) -- from Bondar uCal

**What:** Bondar lets the operator zero the lock-in phase reference at the start
of a session and subtracts that offset from all reported phases (Bondar-uCal.md
§10.1 / Unit1.cpp:2596-2605). Add a `phase_offset_rad` to run metadata + a
"zero phase" UI control; apply post-demod. Useful, non-critical.

### P2-28. Auto-save checkpoints on long runs -- from Bondar uCal

**What:** Bondar flushes an autosave every ~10 min during long ramps
(Bondar-uCal.md §5.3 / Unit1.cpp:556-559); PIONER only writes HDF5 at run end,
so a crash during a multi-hour iso/slow run loses everything. Periodically
flush the in-progress frame to an "in-progress" HDF5 group; move to the final
group on clean completion. Reliability feature.

### P2-29. (front-end) 7-LED calibration-deviation bar -- from Bondar uCal

**(front-end).** **What:** Bondar shows a live LED strip of `Thtr - (Ttpl +
Taux)` lighting at +/-1/2/3/5 C (Bondar-uCal.md §10.10 / Unit1.cpp:2929-3021)
-- at-a-glance calibration-drift feedback. Implement as a small PyQt widget in
the live-monitor panel. UX polish.

> Not borrowed from Bondar (reviewed + rejected): X2 harmonic mode (our FFT
> `harmonics=(1,2,3)` is better), Telnet remote protocol (Tango/HTTP supersedes),
> IOtech driver specifics, hardware-license gate, and the `Sleep(rand())` mains
> de-sync jitter (anti-pattern; integer-cycle alignment is the right fix).
> AD595 low-T correction is already applied (`modes.py:234`); only its
> whole-scan averaging drift remains (already noted, P0-3 area).

---

## P3 — documentation / observability

### P3-1. Document units in `apply_calibration`

See **P0-3**. Doctrine: every numeric operation gets a comment
(`# input: V, output: mV`).

### P3-2. README references `docs/pipeline.md`

**Action:** add a "Pipeline overview" section with one sentence and a
link to `docs/pipeline.md`.

### P3-3. Update Sphinx autodoc against the current package layout

**Action:** `cd docs && make html` — confirm it does not fail.

### P3-4. Public-API docstrings

**Where:** `DaqDeviceHandler.get`, `Calibration.write`,
`IsoMode.ai_stop`, `AiParams/AoParams.channel_count` — currently empty.

### P3-5. Refresh `docs/pipeline.md` with the recent fixes

**Where:** `docs/pipeline.md`, sections "Outstanding TODO" and "AI half-buffer".

### P3-6. Bench-experiment example script

**Action:** `examples/run_slow_with_modulation.py` — set up a program,
modulation, run `SlowMode`, save HDF5, plot.

### P3-7. `mock_uldaq` logs at INFO on every import

**Where:** `src/pioner/back/mock_uldaq.py:50`

**Action:** drop to DEBUG (or fire once per process), or only WARN when
`PIONER_DEBUG=1`.

### P3-8. Review external reference: NanoCalorimetry (J. Gregoire)

**What:** External nanocalorimetry project at
<https://github.com/johnmgregoire/NanoCalorimetry> — possibly relevant
techniques, calibration algorithms, demodulation choices to compare
against ours.

**Action:** Read README and key modules; note any techniques relevant
to our calibration / demod stack; document findings in
[design_notes.md](docs/design-notes.md) or a comparison sub-doc.

### P3-9. Process IR-branch answers and close merge questions

**What:** [docs/ir-merge-answers.md](docs/ir-merge-answers.md) is the
consolidated Q&A document (questions + answers from the IR-branch
developer) covering hardware topology, calibration procedure, algorithm
choices, dead code, and architectural intent. The five blockers
(A1, A2, B1, D1, G1) are all answered.

**Action:** Walk through each answered Q and update mainline doc / code
where the answer clarifies an assumption (especially A1-A3 hardware
topology, B1-B4 calibration procedure, C1 calcaf_lockin canon, D1
apply_fh_cal canon, G1 singleton intent). File follow-up todos for
newly-revealed issues. Mark the Q&A doc as fully processed when done.

---

## Suggested execution order

1. **P0-3** — settled with the physicist (dimensionless Ihtr is intentional);
   do not touch calibration coefficients without a new SI procedure (P2-21).
2. **P1-26 (high)** — open-source / proprietary code-split proposal. Do the
   boundary mapping early; it constrains where later work lands.
3. **Unified arm/start/stop workflow** (P1-17 "Plan 2026-06-05"). Step 1
   (per-mode sample rate + Apply gate) is **DONE 2026-06-05** -- cut slow/iso
   off 20 kHz, reducing the slow-path OVERRUN risk (P1-30). Continue with the
   rest of that plan in order: DiskRecorder -> slow off-ring -> iso two paths
   -> interruptible run + Stop + temp limits.
   - **P1-36 (high, safety)** — chip-presence detection to gate arm/start/stop
     (needs bench confirmation of the probe threshold first); land alongside
     the workflow gating.
4. **P0-5** — no external trigger on the rig; if AO/AI skew matters, do the
   per-host software offset-trim (not the `EXTTRIGGER` loopback). Related:
   P1-37 fast-jitter mitigation.
5. **P1-24 (medium)** — closed-loop PID control (iso hold is now in place as
   the test bed); iso first.
6. **P1-25 (medium)** — AD595 -> MAX6675 / K-type front-end change (needs EE +
   acquisition-path work; coordinate with P1-27 SPICE model).
7. **P1-6 → P1-16** — two or three at a time.
8. **P2-\*** — code-quality round after P0/P1 close.
9. **P3-\*** — last, or piggy-back on each P0/P1 PR.

## Notes

- Run `PYTHONPATH=src .venv/bin/pytest -q` (≤10 s) on every change.
- Front-end work is now in scope (the GUI single-window rewrite has landed);
  front items are tagged **(front-end)** below.
- **Do not change hardcoded names/values** (`Uref`) without an explicit user
  request. Heater channel `"ch1"` now goes through
  `pioner.shared.channels.HEATER_AO` for internal references; the wire format
  stays `"ch{N}"`.
- Before any production run, mandatory smoke on real hardware: fast 1 s
  ramp, slow 2 s with modulation, iso 10 s with modulation. Compare
  against reference data from previous experiments.
