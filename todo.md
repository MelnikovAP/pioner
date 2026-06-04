# PIONER — back-end TODO list

Stepwise, executable backlog of open work on the back-end (no front-end items).
Each item is self-contained: what to do, where, why, and how to verify. **P0**
items go first, **P3** is polish.

File references use the `path/to/file.py:line` format. Test command:
`PYTHONPATH=src .venv/bin/pytest -q`.

## Status

- `pytest tests/`: **100 passed** (mock backend, ~30 s).
- `python -m pioner.back.debug` runs all three modes end-to-end clean.
- Mock-DAQ pipeline verification: see `mock_verification.md` — modulation
  + lock-in confirmed within ~10 % of the analytical amplitude, no sample
  loss, `Uref` tiled correctly for finite / CONTINUOUS / DC-iso paths.
- All "won't run" bugs are closed; remaining work is architectural rough
  edges and physical fidelity items for real hardware.
- Pipeline reference: `spec.md`. Manual mock usage: `mock_verification.md`.

**Conventions kept on purpose:** column name `Uref` (not `Uheater`), and
the `total_ms % 1000 == 0` software constraint on profile durations.
Heater channel `"ch1"` is now the named constant `HEATER_AO` in
`pioner.shared.channels` (see that module for the full layout); the wire
format remains `"ch{N}"`.

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

**Open:** if/when skew matters, implement the software offset-trim. (The
`EXTTRIGGER` loopback validation only applies if a trigger line is ever added.)
Drive a 1 kHz square wave on AO ch1, read it back on AI ch1, find the leading
edge; the fallback options are documented inline in `finite_scan`
(pacer-clock sharing or a per-host software offset trim).

---

## P1 — architectural / logical improvements

### P1-3. `apply_calibration`: in-place mutation of the raw frame is fragile

**Where:** `src/pioner/back/modes.py:195-225`

**What:** the function does `df[4] = df[4] * (1000.0 / hw.gain_utpl)` —
overwriting raw columns. Then it reads `df[5] - df[0] * 1000.0`. The whole
thing is order-sensitive; a future re-ordering would silently produce a bug
that no current test catches because the columns are dropped at the end.

**Action:** introduce local variables (`u_tpl_mv = df[4] * 1000.0 /
hw.gain_utpl`, …) and never mutate raw `df[N]`. The final `df.drop` block
already exists and continues to work.

**Verification:** the existing test suite + a new unit test asserting
that raw integer-named columns are **not** modified before `df.drop`.

### P1-4. Silent modulation clipping to `safe_voltage`

**Where:** `src/pioner/back/modes.py:380-385, 487-488`

**What:** `np.clip(profile, 0, safe_voltage, out=...)` runs without a
warning. If a user sets `Amplitude = 2 V` on top of `DC = 8.5 V` with
`safe = 9 V`, half of the sine period is silently clipped. The waveform
becomes a trapezoid and the lock-in returns a wrong amplitude with no log
trace.

**Action:** before clipping, check `profile.min() < 0` or `profile.max() >
safe_voltage` and emit a `logger.warning` describing how much was clipped.
(Mirror of FIX D, but for the modulated path.)

**Verification:** unit test — a profile that exceeds the safe envelope
should produce a warning record (use `caplog`).

### P1-5. Legacy `IsoMode.run(do_ai=False)` does not actually hold the voltage

**Where:** `src/pioner/back/iso_mode.py`

**What:** the historical "Set V and hold until the GUI presses Off"
scenario still routes through `_mode.run(duration_seconds=0.0)` which
returns immediately and the surrounding `finally: em.stop()` drops the
voltage within milliseconds. P1-1 added the `stop()` primitive that this
fix relies on, but the legacy `do_ai=False` path was not rewired.

**Product answer (2026-06-04):** iso has two intended behaviours.
1. **Default = hold.** "Set V/T" must drive the commanded value and **hold it
   indefinitely** until the operator presses "Off" (or `stop()` is called).
   This is the rewire described below. (Confirmed in review: today the GUI
   "Set" drives only ~1 s then `stop_ao()` drops it — see the
   `_run_iso_streaming` injected path and `IsoMode.run`'s `duration_seconds`.)
2. **Optional timed program.** Also support an iso "temperature program":
   target T (or V) **plus a duration**, after which the run **auto-stops**.
   This is the existing finite-duration path; expose it in the GUI as an
   alternative to the indefinite hold. The two share one code path — a hold is
   just "duration = until Off".

Note the front-end side (a hold vs. timed-program toggle in the iso panel) is
tracked here for context but lands in `front/`, after the back-end rewire.

**Action:**
1. When `do_ai=False`, do **not** route through `_mode.run`. Instead keep
   an `ExperimentManager` instance on `self` and call `em.ao_set(ch, V)`
   (or `em.ao_modulated(...)` if AC is enabled) and **return without
   stopping**.
2. Have `ai_stop()` call the stored `em.stop()` and clear the reference.
   (Currently `ai_stop()` forwards to `_mode.stop()` which is harmless
   but does not stop a held AO since `_mode.run` was never started for
   `do_ai=False`.)
3. Document the new lifecycle: `arm() → run(do_ai=False) → ai_stop()`.

**Verification:** integration test on the mock — `IsoMode(...).run(do_ai=
False)` then read `_shared.iso_voltages` (or the AO buffer) and confirm
the commanded voltage is still being driven; call `ai_stop()` and confirm
`iso_voltages` is empty.

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

### P1-9. Lock-in: `sosfiltfilt` transients on the edges

**Where:** `src/pioner/shared/modulation.py:153-165`

**What:** `filtfilt` is zero-phase, but it has transients of ~10
modulation periods on each edge. The existing test masks this via
`slice(2000, -2000)`. For short scans (<0.5 s at 37.5 Hz) the transient is
>50 % of the signal.

**Action:** return a boolean `valid` mask alongside `(amp, phase)`,
`False` over the transient regions. Document a minimum useful signal
length (`>= 20 / frequency` seconds).

**Verification:** unit test — lock-in on a 0.3 s, 37.5 Hz signal returns a
mask with `False` on the edges.

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
optional injected `ExperimentManager` + `snapshot` callable. The GUI iso
path (`LocalDeviceController._run_iso_streaming`) drives only AO on the
controller's manager and reads AI from the persistent ring (primed
`read_new` cursor -> captures just the run window), stopping only AO
afterwards. The live stream stays active for the whole iso run.
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
(see [docs/Martin-calibration-procedure.md](../docs/Martin-calibration-procedure.md))
with optimization of the polynomial fit stages.

**Action:** Port IR-branch's `CalibrationWizard`
([pioner-IR-branch/pioner_app/ui/calibration_wizard.py](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py))
as the UI scaffold. Adapt the three-stage flow (Thtr / Theater / Ttpl)
to the Martin algorithm specifics. Consider numerical-optimization
improvements (constrained least squares vs unconstrained, robust fit
against melting-plateau outliers). **Depends on P1-17** (live streaming
required for the cursor-pick during ramp). See also B1-B4 in
[docs/ir-merge-answers.md](../docs/ir-merge-answers.md) for
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
CLAUDE.md). Depends on the iso "hold" rewire (P1-5) landing first.

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

---

## P2 — code quality / DX

### P2-1. `pyproject.toml`: drop unused runtime dependencies

**Where:** `pyproject.toml:25-34`

**What:** `matplotlib`, `requests`, `sortedcontainers` are not imported
from `src/`. `tables` is only needed by `_prime_pandas` (which is already
fault-tolerant).

**Action:** move into `optional-dependencies`:
- `matplotlib` → `dev`.
- `requests` → `gui`.
- `sortedcontainers` → remove entirely.
- `tables` → `optional-dependencies.hdf5`.

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
[pioner_app/ui/widgets/simpleProcessWidget.py](../pioner-IR-branch/pioner_app/ui/widgets/simpleProcessWidget.py)
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

### P2-22. Progress bar for slow/iso experiments (low priority)

**Where:** `src/pioner/front/mainWindow.py`

**What:** slow and iso scans run for tens of seconds with no UI feedback.
Add an artificial progress bar driven by elapsed time vs expected
`total_ms` from the armed program. Can be a `QProgressBar` updated by a
`QTimer` in `run_mode()`.

---

## P3 — documentation / observability

### P3-1. Document units in `apply_calibration`

See **P0-3**. Doctrine: every numeric operation gets a comment
(`# input: V, output: mV`).

### P3-2. README references `spec.md`

**Action:** add a "Pipeline overview" section with one sentence and a
link to `spec.md`.

### P3-3. Update Sphinx autodoc against the current package layout

**Action:** `cd docs && make html` — confirm it does not fail.

### P3-4. Public-API docstrings

**Where:** `DaqDeviceHandler.get`, `Calibration.write`,
`IsoMode.ai_stop`, `AiParams/AoParams.channel_count` — currently empty.

### P3-5. Refresh `spec.md` with the recent fixes

**Where:** `spec.md`, sections "Outstanding TODO" and "AI half-buffer".

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
[design_notes.md](../design_notes.md) or a comparison sub-doc.

### P3-9. Process IR-branch answers and close merge questions

**What:** [docs/ir-merge-answers.md](../docs/ir-merge-answers.md) is the
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
2. **P1-5** — iso "hold by default" + optional timed program (auto-stop). The
   `stop()` primitive is in place; rewire the legacy `do_ai=False` / injected
   path so "Set" holds until "Off". Front-end toggle follows.
3. **P1-26 (high)** — open-source / proprietary code-split proposal. Do the
   boundary mapping early; it constrains where later work lands.
4. **P0-5** — no external trigger on the rig; if AO/AI skew matters, do the
   per-host software offset-trim (not the `EXTTRIGGER` loopback).
5. **P1-24 (medium)** — closed-loop PID control (after P1-5); iso first.
6. **P1-25 (medium)** — AD595 -> MAX6675 / K-type front-end change (needs EE +
   acquisition-path work; coordinate with P1-27 SPICE model).
7. **P1-3, P1-4** — independent, do in parallel.
8. **P1-6 → P1-16** — two or three at a time.
9. **P2-\*** — code-quality round after P0/P1 close.
10. **P3-\*** — last, or piggy-back on each P0/P1 PR.

## Notes

- Run `PYTHONPATH=src .venv/bin/pytest -q` (≤10 s) on every change.
- Do not touch the GUI (`front/`) until back-end P0/P1 are closed.
- **Do not change hardcoded names/values** (`Uref`, the
  `total_ms % 1000 == 0` constraint) without an explicit user request.
  Heater channel `"ch1"` now goes through `pioner.shared.channels.HEATER_AO`
  for internal references; the wire format stays `"ch{N}"`.
- Before any production run, mandatory smoke on real hardware: fast 1 s
  ramp, slow 2 s with modulation, iso 10 s with modulation. Compare
  against reference data from previous experiments.
