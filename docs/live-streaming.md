# Live AI streaming for PIONER modes

Design document. Defines how PIONER handles continuous AI sampling, live
UI updates during experiments, between-experiment chip monitoring, and
external-trigger synchronization with collaborating instruments
(synchrotron, Raman, etc.).

**Status:** design converged, not yet implemented. See section 11 for
the open hardware-soak validation points and section 12 for the
decision log explaining how we got here.

Related docs:
- [modulation.md](modulation.md) -- demodulation theory; this doc
  references the lock-in / FFT primitives discussed there.
- [usb-2637-vs-2627.md](usb-2637-vs-2627.md) -- hardware capabilities
  that constrain this design (single-ended only, independent AI/AO
  pacer clocks, TTLTRG hardware trigger, channel queue).
- [../known-issues.md](../known-issues.md) section 1 -- FIFO overrun
  history; the streaming design must not regress this.
- [../design_notes.md](../design_notes.md) -- AO/AI trigger sync
  architecture.
- [../postmortem/2026-05-23-differential-vs-defaultio.md](../postmortem/2026-05-23-differential-vs-defaultio.md)
  -- the DIFFERENTIAL fallback removal that anchors the
  USB-2637-specific assumptions here.

---

## 1. The problem

Three load-bearing requirements:

1. **Mid-experiment streaming.** During slow/iso/calibration runs (which
   last from minutes to days), the UI must show fresh measurements
   on ~100-250 ms cadence -- temperature, AC amplitude, phase, power --
   rather than waiting until the run finishes. Fast-heat (3-10 s) is
   explicitly out of scope; it keeps its current block-mode behaviour.
2. **Between-experiment chip monitoring.** Before launching any
   experiment, the operator must see whether the chip is alive (Ttpl
   reads ambient, AC modulation produces a sane amplitude on the
   thermopile, current loop is closed, etc.). Running an experiment to
   verify the chip is alive wastes a sample. Critical for the workflow.
3. **External-trigger synchronization.** PIONER must integrate with
   other analytical instruments (synchrotron beamline, Raman
   spectroscope, X-ray diffractometer) where one measurement triggers
   another. The chip sits in the beam path; the beamline emits a TTL
   pulse on TTLTRG; PIONER captures the chip's thermal response
   synchronized with that pulse, with no lost initial samples.

Constraints we've established:

- **One experiment at a time.** PIONER is single-user, single-experiment.
  No concurrent recording of fast-heat + slow-heat.
- **AI parameters can be uniform across all modes.** Production config:
  20 kHz sample rate, 6 single-ended channels (Uref, Umod, Utpl, Uhtr,
  Uaux, Uhtrabs), range +/-5 V, on USB-2637 which is single-ended only.
  We do not need to reconfigure AI between modes.
- **Recording must not regress the 1 s fast-heat use case.** A 500 ms
  gap in the recorded data is scientifically unacceptable when the
  experiment itself only lasts a second or two.
- **Refactor of tests and the experiment-manager API is acceptable**;
  Tango compatibility is deferred (revisit later); we're locked to MCC
  USB-2637 hardware.

---

## 2. Two layers: raw samples vs engineering quantities

A common source of confusion: "stream AI to the UI" actually means two
unrelated layers.

**Layer 1 -- raw samples (~120 kS/s).** Voltage on each of 6 AI channels,
sampled at 20 kHz. The DAQ DMAs these into a host buffer. Useless to
plot directly: too fast, raw voltages don't mean anything to the
operator.

**Layer 2 -- engineering quantities (~5-10 Hz).** What the UI actually
shows: Ttpl in degrees C, Thtr in degrees C, Ihtr in mA, AC response
amplitude in Kelvin or millivolts, phase in degrees, power in watts.
These are computed from Layer 1 by **demodulation**: sin/cos multiply
of a window of raw samples against the AO reference, followed by a
low-pass or by an FFT (see [modulation.md](modulation.md)).

Producing Layer 2 from Layer 1 in real time is the part most of this
document is about.

Three demodulation strategies were considered:

| Strategy                        | Cost           | Drift accumulation | Implementation |
|---------------------------------|----------------|--------------------|-----------------|
| Demod the entire accumulated array on every UI tick | O(N) per tick, N grows with time -- breaks after minutes | None | Trivial   |
| Stateful chunked demod (filter state preserved across calls) | O(chunk) per tick, scales | None | ~100 lines, careful |
| Sliding-window demod -- demod last K modulation periods on each tick, stateless | O(K) per tick, K fixed and small | None (each tick independent) | ~10 lines |

**Decision: sliding-window demod (third row).** Validated by the
IR branch in production for the same problem
(`analyze_slow_heating_chunk`). At f=37.5 Hz with K=5 periods, the
window is 5/37.5 = 0.13 s = 2600 samples; the demod cost per tick is
microseconds; one (t, A, phi) point per tick goes onto the plot.
Visually indistinguishable from the stateful chunked demod. Revisit
only if operator reports the noise floor of independent-window
estimates is too high.

---

## 3. Final architecture: persistent AI + dormant disk recorder

Three converged design rules:

### Rule 1 -- AI scan runs continuously from Connect to Disconnect

A single AI scan is started at `daq.connect()` with the production
parameters (sample rate, channels, range, queue) and runs in
`ScanOption.CONTINUOUS` mode until `daq.disconnect()`. **It is never
stopped or reconfigured during normal operation.** Every other component
in the system reads from this scan.

Why: every mode handoff (Monitor -> SlowMode -> Monitor, or Monitor ->
EXTTRIGGER-armed -> trigger fires) that requires stop/restart of AI
introduces a 100-500 ms gap. For 1 s fast-heat experiments that gap is
catastrophic. For external triggers the gap creates a race window where
the trigger could be missed entirely. Keeping AI alive eliminates the
entire class of failure.

### Rule 2 -- One in-RAM ring buffer feeds all live readers

The existing `start_ring_buffer` / `snapshot_ring_buffer` primitive in
[`back/experiment_manager.py:259`](../src/pioner/back/experiment_manager.py#L259)
provides the substrate. We extend it with:

```python
def peek_ring_buffer(self, samples: int) -> np.ndarray:
    """Last N samples, do not advance any cursor."""

def read_new_ring_buffer(self, consumer_id: str) -> np.ndarray:
    """Everything since this consumer's last call; advance its cursor.
    Multiple consumers, each with private cursor."""
```

Ring buffer size: **~2 seconds** (~240 kS, ~2 MB). Just enough for the
UI sliding-window demod plus a comfortable safety margin against
Python GIL stalls and USB hiccups. Older samples are silently
overwritten -- the ring is **lossy by design** because it is for live
display, not for the canonical record (that's Rule 3).

Multiple consumers safely share this ring:
- **UI Values widget**: `peek_ring_buffer(N=sliding_window)` on a
  250 ms QTimer. Read-only, no cursor.
- **UI live plot for slow/iso/calibration**: same shape, 100 ms QTimer.
- **Disk recorder** (when active): `read_new_ring_buffer("recorder")`
  on its own thread, drains everything new since previous call.

Reads and writes are guarded by the existing `_ring_lock`.

### Rule 3 -- Disk recorder is dormant by default, active from Arm to experiment end

The recorder is a separate background thread that owns an open
`HDFStore` and dumps samples into it incrementally. **It only exists
during an experiment.**

Lifecycle:

```
operator presses "Arm" (any mode):
  recorder = DiskRecorder(experiment_metadata)
  recorder.start()   # opens HDF5 file, spawns worker thread
                     # worker: read_new_ring_buffer("recorder") every 500 ms
                     # appends each chunk to the HDFStore

(if EXTTRIGGER mode)
  AO armed with EXTTRIGGER
  UI: signal "Ready" via DIO output
  (beamline fires whenever, possibly seconds or minutes later)
  AO starts on trigger (hardware-fast, 1 us + 1 clock cycle)
  recorder keeps draining ring buffer the whole time

(if internal-start mode)
  AO scan started immediately
  recorder keeps draining ring buffer

experiment AO finishes (or operator stops):
  recorder.stop()       # worker drains the remaining ring contents
                        # closes the HDFStore
  AO returns to monitoring state
```

Pre-trigger data is captured **automatically** because the recorder
started at Arm, before the trigger. If the operator armed 30 seconds
before the beamline fired, the file contains those 30 seconds of
pre-trigger baseline. The duration of pre-trigger data == operator-
controlled time between Arm press and trigger fire. **There is no
configuration parameter for "pre-roll length"** -- it's just the wall
clock.

This is the simplest design that satisfies the "no missed initial
samples" requirement: by the time the trigger could possibly fire, we
were already recording for at least the AO-arm duration. Trigger fires;
AO starts hardware-fast; AI was already streaming; the data is captured
naturally.

---

## 4. AO behaviour per mode

AI is fixed (Rule 1). AO varies per mode.

| Mode             | AO state                                                                  |
|------------------|---------------------------------------------------------------------------|
| Idle (no experiment, no Arm) | "Monitoring drive": baseline + optional AC modulation. AC defaults to ON using config.json modulation params (f=37.5 Hz, amp=0.1 V, offset=0.3 V). Power dissipation ~6 uW, negligible. Operator can toggle AC off via UI for a fully passive readout. |
| FastHeat (Armed) | AO finite scan with the fast-heat profile. `ScanOption.DEFAULTIO`, host buffer sized to the full scan length (see [../known-issues.md](../known-issues.md) section 1 for why DEFAULTIO not CONTINUOUS). |
| SlowMode (Armed) | AO finite scan with the slow ramp + AC modulation profile, sized to the full ramp length. |
| IsoMode (Armed)  | AO CONTINUOUS scan with one-second modulated buffer that wraps cleanly (verified by `check_ao_period_integrity` from `shared/modulation.py`). |
| EXTTRIGGER variant of any of the above | AO armed with `ScanOption.EXTTRIGGER` -- DMA loaded, ADC sequencer ready, waiting for TTLTRG. Fires on trigger edge. |

Transitions between AO states happen on Arm (idle -> experiment) and at
experiment end (experiment -> idle). Each transition involves an AO
scan stop + new scan arm, ~30 ms over USB. During this transition AO is
briefly at "DACs cleared to zero scale: 0 V +/-150 mV"
(per USB-2637 datasheet, table 5). The chip sees a momentary AO=0,
same as today.

**AI sees no transition. The ring buffer keeps filling. The recorder, if
active, keeps reading.**

---

## 5. External-trigger flow in detail

The motivating use case: chip sits in synchrotron beam path. Beamline
fires X-ray pulse; PIONER simultaneously starts a fast-heat profile and
records the chip's thermal response.

```
1. Connect: AI scan starts (CONTINUOUS), runs.
2. UI: Monitoring shows live Ttpl, Ihtr, Rhtr, phi.
   Operator verifies chip is alive.
3. Operator: loads fast-heat profile, sets EXTTRIGGER flag.
4. Operator: presses Arm.
   a. UI stops "monitoring AO" (the AC drive).
   b. UI arms AO with profile and ScanOption.EXTTRIGGER.
      AO is now waiting for TTLTRG.
   c. UI starts DiskRecorder. HDF5 file opened.
      Recorder begins reading ring buffer.
   d. UI raises a DIO output line ("Ready").
5. Beamline sees "Ready", schedules X-ray pulse.
   (Time elapsed since Arm: from milliseconds to minutes,
    operator/beamline-controlled. Recording continues throughout.)
6. Beamline fires TTLTRG.
7. AO starts on TTL edge (1 us + 1 clock cycle latency, per datasheet).
8. AO profile runs. AI continues filling ring buffer.
   Recorder continues writing.
9. AO completes (e.g., 1 s fast-heat profile done).
10. UI stops recorder. HDF5 file closed.
11. UI lowers "Ready" DIO line.
12. AO returns to monitoring drive.
13. Monitoring resumes seamlessly (AI never paused).
```

Key properties:

- **No missed initial samples**: recorder was active before trigger.
- **No race condition**: trigger arrives strictly after Arm completes
  (operator-controlled handshake; standard beamline practice).
- **AO + AI synchronized on trigger edge**: both armed with EXTTRIGGER
  (in the fast-heat case AO arms with the profile; AI already runs
  CONTINUOUS but its sample number at trigger time can be recovered
  via the device's `get_scan_status().current_scan_count`).
- **Pre-trigger baseline length = time between Arm press and trigger
  fire**. Operator controls. Typical: a few seconds for "ready,
  beamline, when you're ready" handshakes.

Sample-accurate alignment between trigger event and AI sample index --
if the experiment needs better than ~10 ms precision -- requires routing
TTLTRG to a counter input (CNT0-CNT3 on USB-2637, ~50 ns precision via
the 20 MHz counter clock) in addition to the TTLTRG line. This is an
optional enhancement, deferred to when the first synchrotron run is
planned. For now, the host's polling of `get_scan_status()` at
trigger detection gives ~10 ms accuracy, which is adequate for
slow-heat and most fast-heat cases.

---

## 6. What this design explicitly does NOT include

- **No MonitorMode class** in `back/modes.py`. Monitoring is the natural
  default state of the system (AI streaming, AO at baseline+AC, UI
  reading from ring buffer). It does not need a dedicated mode object.
- **No observer/subscriber callback registration.** Consumers pull from
  the ring buffer when they want, with private cursors. No background
  push.
- **No global singleton object** in the IR-branch sense (no
  `DAQController._instance`, no owner tags). The
  `ExperimentManager` is the natural place for the persistent AI scan
  and ring buffer; modes do not own AI but they don't fight over it
  either (they only touch AO).
- **No changes to FastHeat block-mode UX.** Fast-heat from the UI button
  still completes in 3-10 s and shows the result at the end. Streaming
  is for slow/iso/calibration during the run, plus monitoring between
  runs, plus EXTTRIGGER capture (including fast-heat triggered
  experiments).
- **No TTL-based on-disk pre-roll.** We do not write to disk between
  experiments. Pre-trigger data lives in HDF5 starting at Arm; before
  Arm, no disk record exists.
- **No Tango server rework right now.** Tango currently builds
  `ExperimentManager` per call. Adapting it to the persistent-AI design
  is a separate task, deferred. The local GUI workflow does not depend
  on Tango; for now we accept that running Tango concurrently with the
  local GUI is unsupported and an error will be raised if attempted.

---

## 7. Per-mode behaviour summary

| Mode             | AI behaviour                                  | AO behaviour                                                 | Disk recorder                  | UI live display                                |
|------------------|-----------------------------------------------|--------------------------------------------------------------|--------------------------------|-------------------------------------------------|
| Idle             | CONTINUOUS, ring buffer fills, ~2 s in RAM     | Monitoring AC (default) or 0 V (operator toggle)             | dormant                        | Values sidebar ticks 250 ms                    |
| FastHeat         | CONTINUOUS, same scan                         | DEFAULTIO finite, full profile buffer                        | active Arm -> end              | Values sidebar; progress bar; result tab at end |
| SlowMode         | CONTINUOUS, same scan                         | DEFAULTIO finite, ramp+AC profile                            | active Arm -> end              | Values sidebar; slow-heat plot every 100 ms via sliding-window FFT |
| IsoMode          | CONTINUOUS, same scan                         | CONTINUOUS modulated, buffer integer-cycle (`check_ao_period_integrity`) | active Arm -> Stop button | Values sidebar; iso plot ticking 100-250 ms    |
| Calibration      | CONTINUOUS, same scan                         | Three-stage drive per `CalibrationWizard` (V ramp or T ramp; AC may or may not be present per stage) | active per stage | Cursor-pick plot during each stage             |
| Any of above with EXTTRIGGER | CONTINUOUS, same scan         | EXTTRIGGER flag added, waits for TTLTRG; otherwise per-mode  | active from Arm (which is **before** trigger) | live during the wait + during the run |

The recorder lifecycle is identical across modes: open file at Arm,
drain ring on a worker thread, close file at experiment end.

---

## 8. Implementation plan

### Back-end work (~3-4 days)

1. **Modify `ExperimentManager`** to keep the AI scan persistent across
   the manager's lifetime:
   - `__init__` does not start AI.
   - New `start_persistent_ai(ai_channels, max_seconds)` -- called once
     at Connect. Begins the CONTINUOUS scan, spawns `_ring_loop`.
   - New `stop_persistent_ai()` -- called once at Disconnect.
   - Existing `finite_scan` repurposed: still arms AO (with or without
     EXTTRIGGER), but reads AI from the persistent ring buffer rather
     than starting its own scan.
2. **Add ring-buffer extensions**:
   - `peek_ring_buffer(samples: int) -> np.ndarray`
   - `read_new_ring_buffer(consumer_id: str) -> np.ndarray` with
     per-consumer cursor storage.
3. **Add `DiskRecorder`** class (`back/disk_recorder.py`, ~150 lines):
   - Owns an `HDFStore`, a worker thread, a private ring cursor.
   - `start(metadata)` -> opens file with metadata in HDF5 attrs.
   - Worker pulls `read_new_ring_buffer` every 500 ms, appends to store.
   - `stop()` -> drains remaining ring, closes file, joins worker.
4. **Refactor `FastHeat`, `SlowMode`, `IsoMode`** to:
   - Not start AI -- assume it's already running on the manager.
   - Arm only AO with `EXTTRIGGER` flag when requested by caller.
   - Spawn `DiskRecorder` at the start of `run()`, stop it at end.
   - Return DataFrame loaded from the recorder's HDF5 file (not from
     in-memory accumulation).
5. **Add `MonitorAO` helper** -- single small class that maintains the
   "monitoring AC drive" between experiments. Started on Connect (with
   default AC params from config.json), stopped on Arm of any
   experiment, restarted on experiment end. ~50 lines.
6. **Tests**:
   - `peek_ring_buffer(N)` returns N samples; does not advance.
   - `read_new_ring_buffer(id)` returns delta, advances per-id cursor.
   - Persistent AI: start, run for 5 seconds via mock, verify ring fills.
   - `DiskRecorder` lifecycle: arm-record-stop produces a valid HDF5
     with the expected dataset shape.
   - SlowMode under the new model: arm + finite AO scan + recorder
     produces a complete DataFrame on read-back.
   - EXTTRIGGER variant: AO armed but not started until trigger event
     emitted by mock.

### Front-end work (~1 week, when we get there)

1. **At Connect**: UI starts persistent AI on the manager, starts
   MonitorAO (default config.json modulation), starts Values-sidebar
   QTimer (250 ms).
2. **At Disconnect**: stop MonitorAO, stop persistent AI.
3. **Slow-heating widget**: own QTimer (100 ms), sliding-window FFT,
   live plot.
4. **Calibration wizard port**: live plot per stage via the same
   pattern.
5. **Arm/Stop buttons**: stop MonitorAO; call mode's `arm()` and
   `start()`; recorder activates inside the mode; restart MonitorAO at
   end.
6. **EXTTRIGGER UI**: checkbox on each mode panel; when checked, mode's
   `arm()` adds the trigger flag; a separate "Ready signal" indicator
   light reflects the DIO output state.

### Hardware soak test (~1 week, before production deployment)

1. **Stability of persistent AI** under continuous CONTINUOUS scan over
   several hours: no FIFO overrun (current 4 kS AI FIFO, ~34 ms host
   stall budget at 6 ch x 20 kHz -- see [usb-2637-vs-2627.md](usb-2637-vs-2627.md)).
2. **AO state transitions** when arming/stopping experiments while AI
   is running: verify the chip sees the expected AO output, no AI
   glitches.
3. **EXTTRIGGER capture** via DIO loopback (drive TTLTRG from a DOut
   pin) -- 100 iterations to confirm the recorded file always contains
   the trigger-aligned data with the expected pre-trigger baseline.
4. **Multi-hour iso run** to confirm `DiskRecorder` keeps up with
   long-running streams (1 MB/s sustained for hours, HDF5 file growth
   to 10+ GB).

---

## 9. Disk usage and file structure

| Period               | Rate          | Per hour          | Per day          |
|----------------------|---------------|-------------------|------------------|
| Monitoring (no rec)  | 0             | 0                 | 0                |
| Mid-experiment       | ~1 MB/s        | ~3.5 GB           | ~84 GB (iso multi-day) |

File path convention (matching `back/modes.py::save_run_to_h5`):

```
<data_path>/<mode>_<YYYYMMDD_HHMMSS>.h5
  data/
    Uref, Umod, Utpl, Uhtr, Uaux, Uhtrabs   (raw, in volts)
    time, Taux, Thtr, temp, temp-hr, ...    (engineering, post-demod)
    temp-hr_amp, temp-hr_phase              (slow/iso only)
  calibration                               (JSON-serialised)
  settings                                  (JSON-serialised)
  temp_volt_programs/<channel>              (per-channel program)
  voltage_profiles/<channel>                (per-channel AO buffer)
  metadata                                  (HDF5 attrs: trigger source, arm/end timestamps, EXTTRIGGER flag, etc.)
```

For multi-day iso runs the HDF5 file will exceed 80 GB. PyTables /
HDFStore handles this but per-day file rotation (one file per 24 hours,
post-processed concatenation if needed) is a sensible addition. **Not
in scope for the initial implementation**; revisit if iso runs of
>24 h become routine.

---

## 10. Caveats and known sensitivities

### Drift during long persistent AI scans

USB-2637 datasheet does not specify long-term continuous-scan
stability. Possible failure modes during hours-long CONTINUOUS scans:

- Driver-side memory leak in `uldaq` (unlikely but unverified).
- Cumulative timing drift in the ADC pacer relative to wall clock
  (matters only for absolute time stamping; relative timing within
  the scan is fine).
- Buffer-handling glitch when `current_scan_count` wraps around its
  32-bit limit (at 120 kS/s aggregate, 32-bit wraps at 2^32 / 120000
  / 3600 / 24 = ~414 days; not an issue for normal use, but worth
  being aware of).

Must be validated in hardware soak (section 8).

### AI parameters locked across all modes

Production AI: 20 kHz, 6 ch, +/-5 V range, all single-ended. This is the
same across FastHeat, SlowMode, IsoMode, Calibration. If a future
requirement says "fast-heat needs 100 kHz, slow-heat needs 10 kHz"
this design has to change (or AI is reconfigured at mode boundaries
again, reintroducing the gap problem). For now operator confirmed the
production config is uniform.

If per-mode AI gain queues are needed later (different channels want
different ranges in different modes), USB-2637's channel queue
supports up to 64 elements -- it can be reloaded without stopping the
scan via `a_in_load_queue`. ~20 extra lines, not in scope now.

### State leakage in `ExperimentManager` across long sessions

With a persistent AI scan, the manager lives from Connect to
Disconnect. Bugs that leak state (uncleared flags, dangling thread
references) accumulate over hours. Mitigation: deliberate state-reset
hooks in `arm()` / `run()` / experiment end, plus a "self-check" log
line every minute reporting ring fill level, recorder backlog, AO
status. Standard observability.

### MonitorAO with AC stresses the chip continuously

Power-budget check confirms negligible: ~6 uW at production modulation
amplitude on a 1700 Ohm heater. Well below any thermal time constant
that matters. Operator can disable via UI toggle for a strict passive
mode. Closed open question (was O3 in earlier revision of this doc).

### Tango deferred

Mainline Tango server (`back/nanocontrol_tango.py`) builds
`ExperimentManager` per call -- it does not share the persistent AI
session that the local GUI uses. If both are run on the same DAQ they
will fight; raise a clear error if the Tango client connects while the
local GUI holds the persistent scan, document it as "concurrent local
GUI + Tango unsupported in this release". Revisit Tango re-architecture
separately.

### Sample-accurate trigger timestamping

Default trigger detection -- host polls `get_scan_status()` in a 10 ms
loop -- gives ~10 ms accuracy on the trigger-to-sample mapping. For
synchrotron experiments where 1 ms matters, route TTLTRG also to a
counter input (CNT0..3) and read the counter at scan start. ~50 ns
precision via the counter's 20 MHz input clock. Deferred until a
specific synchrotron run requires it.

---

## 11. Open questions

Smaller list after the design converged:

- **Q1. AO baseline between experiments -- 0 V or some offset?** Current
  proposal: 0 V on heater channel + AC modulation. But the historical
  `reset_ao_outputs(ao0=0.1, ao1=0.0)` pattern uses 0.1 V on ch0
  (presumably a deliberate baseline). What's the right value?
- **Q2. AC modulation defaults configurable per-session?** Operator
  may want different defaults for different chips (some chips don't
  tolerate even 6 uW continuous). Should this be in `config.json`
  per-chip, or always from a single global default?
- **Q3. Calibration wizard's run-mode AO behaviour during pre-Arm
  stages.** The wizard has UI dialogs between stages (cursor pick,
  polynomial fit). Should MonitorAO drive during those dialogs, or be
  off? Probably on (chip stays in a known thermal state) but worth
  confirming with operator.
- **Q4. What happens if the operator presses Stop mid-experiment?**
  Current spec: recorder closes the file in whatever state, mode's
  `finalize()` returns whatever was captured. Add a `partial=True`
  flag in the file metadata so post-processing knows.
- **Q5. Disconnect-during-experiment behaviour.** Operator hits
  Disconnect with a recorder running. Spec: stop recorder, close file
  (mark partial), stop AI, release device. Verify no thread leaks.
- **Q6. Recovery from AI scan death.** If the persistent AI fails
  mid-session (e.g., USB cable bumped), how does the system surface
  this? Watchdog: if `get_scan_status()` returns `IDLE` unexpectedly,
  UI shows red "DAQ disconnected" indicator and disables Arm. Manual
  user re-Connect required.

---

## 12. Decision log

This section captures **how we arrived at the current design**, so a
future maintainer can read the chain of reasoning rather than just the
conclusion. Skip if you only want the design.

### Initial proposal: variant A (per-mode AI)

First proposed shape. Each mode arms its own AI scan, runs, stops.
MonitorMode introduced as a fourth mode that arms an AI scan + AC drive
between experiments. Looked clean: minimal architectural change,
existing IsoMode `start_ring_buffer` reused, Tango untouched.

### Pushback: mode handoff is the bug factory

Identified handoff races as the single largest residual risk:
pause/resume AI scans across mode boundaries depends on USB-driver
release timing, autogain reconfigure, and Python state machine
correctness. IR branch has these races and they manifest as bugs.
Mitigation requires explicit state machine + watchdog + hardware soak
testing. Solvable but real work.

### Counter-proposal: variant B (singleton)

Suggested the IR-branch shape: one global AI session, modes only
command AO. Initially evaluated as overkill: it doesn't actually
eliminate the handoff problem (AI params still change between modes
in IR-branch, so AI still restarts).

### Constraint that changed the calculus

Operator clarified: AI parameters can be **uniform across all modes**
on USB-2637. Same sample rate, same channels, same range. The only
thing that varies is AO. With this constraint, the AI scan does **not
need to restart** at mode transitions, which removes the handoff
problem from the singleton design entirely.

Singleton-fixed (singleton + fixed AI params) became the actual
candidate: AI never restarts, no handoff races, less code, simpler
mental model. The remaining concerns (Tango rewrite, test refactor,
state leakage) were either deferred by operator (Tango) or accepted as
manageable (tests, observability).

### External trigger requirement reinforces persistent AI

Operator added: external trigger from synchrotron / Raman is a hard
requirement (the scientific method is multi-instrument combination).
Even with operator-controlled trigger timing, persistent AI is more
robust than per-mode arm-with-EXTTRIGGER: the experiment's recording
window starts from Arm, before trigger, automatically capturing
pre-trigger baseline without needing a separate "baseline" file or a
500 ms gap.

### Data volume forced disk streaming

Slow ramps over hours / iso runs over days -> 80 GB/day raw. Cannot
accumulate in memory. Solution: dormant disk recorder activates at Arm,
drains the ring buffer to HDF5 in real time, closes file at experiment
end. Same pattern as mainline's `_collect_finite_ai` half-flip but
shared across all modes via the ring buffer abstraction.

### Final simplification: recording starts at Arm, not at trigger

Earlier we discussed pre-roll: pull last N seconds from the ring buffer
at trigger detection. Operator pointed out that starting the recorder
**at Arm** is simpler: the file naturally contains everything from Arm
to experiment end, including pre-trigger baseline of whatever length
the operator chose. No RAM-bounded pre-roll length, no backfill logic,
no TTL cleanup. Just open the file at Arm and close at end.

This is the design captured in section 3 and following.

### Why not just IR-branch's `DAQController`?

IR-branch's singleton works for monitoring between experiments
(historically what it was designed for) but its API has accumulated
debt: tagged owner system, race conditions on stop, ambiguous return
values from `start_acquisition`, implicit AC drive that's hard to
disable. We reuse the **shape** (persistent AI + per-mode AO) but
implement it fresh in the existing `ExperimentManager` to avoid
inheriting those bugs.

---

## 13. Alternative architectures (not chosen, preserved for reference)

The current design (§3) is the one we converged on. Two other shapes
came up in discussion and are documented here in concrete detail so a
future maintainer can fall back to them if the current design hits a
blocker (see "When to revisit" at the end of this section).

### 13.1. Variant A: per-mode AI session

Each experiment mode arms its own AI scan via
`ExperimentManager.start_ring_buffer(...)` on `start()`, runs, and
stops the scan on `stop()`. **No persistent AI between experiments.**
This is the shape closest to today's `IsoMode` extended uniformly to
SlowMode and Calibration.

Lifecycle:

```
operator presses "Arm":
  mode.start()
    -> em.start_ring_buffer(ai_channels, max_seconds=10)
    -> em arms AO with profile (or with EXTTRIGGER flag)
  ... operator waits, or trigger fires ...
  ... mode runs ...
mode.wait_or_stop()
  -> em.stop_ring_buffer()  # stops AI scan
  -> close HDF5 file
  -> AO returns to 0 V or disabled
```

UI live-display reads `em.peek_ring_buffer(N)` on a QTimer during the
run. The mode also runs the disk recorder internally for the duration
of the run.

**Trade-offs:**
- Pro: smallest change from current code. ~100-150 lines to add
  `peek` / `read_new` and to split `SlowMode.run()` into
  `start/wait/finalize`. Existing 52 tests survive without modification.
  Tango server keeps working (still builds `ExperimentManager` per
  call, no global state to share).
- Con: **between experiments, no AI is running.** The "verify chip is
  alive before launching an experiment" requirement is not addressed.
  Operator presses Arm blindly.
- Con: every Arm starts a new AI scan -- on USB-2637 that's a
  ~30-50 ms USB round-trip to set up the scan, followed by the first
  samples arriving. For 1 s fast-heat experiments triggered externally
  this gap is unacceptable. The trigger can fire while AI is still
  setting up -> missed trigger or partial first window.

**When to revisit:** if per-mode AI parameter differences become a
requirement (e.g., one mode wants 100 kHz, another 10 kHz), the
persistent-AI assumption of the current design fails. Variant A
naturally accommodates per-mode AI params because each mode owns its
own scan.

### 13.2. Variant A + MonitorMode

A with a fourth pseudo-mode `MonitorMode` that runs whenever no real
experiment is active, providing the "live values between experiments"
that variant A alone lacks. The shape is closest to what IR-branch
does, but with explicit handoff state rather than IR-branch's owner
tags.

Lifecycle:

```
After Connect:
  ui.start_monitor()
  monitor.start()
    -> em.start_ring_buffer(ai_channels, max_seconds=2)
    -> em.ao_modulated(monitor_modulation_params)
  UI Values sidebar polls em.peek_ring_buffer(N) every 250 ms

Operator presses "Start slow heat":
  ui.pause_monitor()
  monitor.pause()
    -> em.stop_ring_buffer()  # waits for ScanStatus.IDLE
    -> em.ao.stop()
  SlowMode.start()
    -> em.start_ring_buffer(ai_channels, max_seconds=10) # new scan, possibly new params
    -> em.ao.scan(slow_profile)
  ... slow heat runs ...
  SlowMode.finalize()
  ui.resume_monitor()
  monitor.resume()
    -> em.start_ring_buffer(...) (yet another new scan)
    -> em.ao_modulated(monitor_modulation_params)
```

State machine (UI-orchestrated, not embedded in the modes):

```
IDLE -> MONITORING -> HANDOFF_TO_EXPERIMENT -> EXPERIMENT
                                                  |
                          HANDOFF_TO_MONITOR  <---+
                                  |
                                  v
                              MONITORING
```

Each `HANDOFF_*` transition has explicit guards:
- Active polling of `ai.get_scan_status() == IDLE` (10 ms tick,
  max wait 500 ms) before re-arming.
- UI shows the current state in a status indicator so the operator can
  tell whether a handoff is in progress vs stuck.

Disk recorder follows the same shape as the converged design (dormant
between experiments, active per experiment), so this variant differs
from the current design **only in AI ownership**.

**Trade-offs:**
- Pro: each mode is self-contained; symmetric with FastHeat / SlowMode
  / IsoMode design pattern. New maintainer reading the code sees four
  similar mode classes, not "three modes + a global persistent AI
  managed elsewhere".
- Pro: per-mode AI params naturally allowed (each handoff is a chance
  to reconfigure).
- Pro: Tango unchanged.
- Con: **handoff race conditions are real and the single largest
  residual risk**. The state machine + watchdog + hardware soak test
  are mandatory. ~150-200 lines of UI orchestration code on top of the
  back-end work.
- Con: every Arm still has the ~30-50 ms gap problem from variant A.
  Even with MonitorMode keeping AI alive between experiments, the
  transition to an experiment-armed AI scan introduces a gap.
  Mitigated for EXTTRIGGER experiments only if the operator's "Ready"
  signal happens **after** Arm completes (which is the same operator
  handshake we'd need anyway).
- Con: between-experiments AC modulation is implicit in the
  MonitorMode AO state, but switching it during experiments requires
  the explicit pause/resume choreography.

**When to revisit:** if persistent-AI proves unreliable on the actual
USB-2637 hardware (e.g., the driver leaks memory over multi-hour
sessions, or the scan dies after some duration), per-mode AI sessions
that are explicitly bounded may be more robust. The cost is the
handoff machinery.

### 13.3. Variant B: IR-branch-style singleton

The IR branch implements a global `DAQController` singleton with
`acquisition_owner` tags. AI is started by whichever widget claims it
first, with the tag denoting current ownership. Other widgets get
read access via `peek_data`. Ownership transfers on `start_acquisition`
calls with new owner.

The current converged design (persistent AI in `ExperimentManager`) is
**a cleaner version of this**: same physical pattern (one AI scan
spanning multiple modes), but without the implicit ownership transfer.
Modes never claim AI ownership in our design; they only command AO.

We do not reuse the IR-branch implementation because:
- Ownership transfer races are observed bugs in IR-branch
  (multiple try/except blocks mask half-released ownership state).
- `start_acquisition` return values are not consistently documented
  (True/False/None across branches).
- `_acquisition_owner` is mutated from multiple call sites with no
  clear invariant.
- The mock backend (`fake_daq.py`) does not exercise these paths,
  so the bugs only manifest on real hardware.

**When to revisit:** never, in this form. If we need owner-tagged
multi-consumer access (e.g., simultaneous Tango + GUI), reimplement
the concept fresh on top of the current design rather than porting
IR-branch code.

### 13.4. Dual implementation with config switch (consideration, not committed)

Instead of committing to one architecture upfront and hoping hardware
behavior matches, **implement both singleton-fixed (§3, primary) and
A+MonitorMode (§13.2) behind a common interface, switchable by config
flag**, validate empirically over a defined trial period, then **retire
the loser**. This subsection documents what that would look like
concretely so the decision to do this (or not) can be made on
information rather than guesswork.

#### When dual implementation is justified

All three should hold:

- **Real uncertainty about hardware behavior.** USB-2637 long
  continuous-scan stability is not in the datasheet; multi-hour
  CONTINUOUS scans are not exercised by any existing test. If we
  expect to find something unexpected on real hardware, having both
  options is a real hedge.
- **Schedule slack.** Dual costs ~30-40% more back-end work than one
  variant alone (most code is shared, see cost table below). If we
  don't have ~5 weeks instead of ~3, dual is not worth the bit-rot
  risk.
- **Willingness to commit to a deadline.** Without explicit "retire
  the loser at date D" discipline, the dual implementation becomes
  permanent technical debt.

If any of these is false, do not do this. Pick one variant up-front
and let §13 stand as the documented fallback in case of disaster.

#### Cost split: most code is shared

```
       Shared infrastructure
       (~400 lines back-end + ~150 lines front-end)
         |
         |- ring buffer + peek/read_new + per-consumer cursors
         |- DiskRecorder class (open at Arm, drain, close at end)
         |- AO transition handling (monitoring -> experiment -> monitoring)
         |- EXTTRIGGER arming logic
         |- Sliding-window FFT demod stack
         |- HDF5 schema + metadata
         |
         |---> PersistentAIProvider (~100 lines)
         |       AI scan started on Connect, stopped on Disconnect
         |       Modes do not touch AI
         |
         '---> PerExperimentAIProvider (~200 lines)
                 AI scan armed by each mode on start()
                 MonitorMode class + pause/resume/state machine
                 Watchdog for handoff failures

   Config flag selects which provider is instantiated at Connect.
   Everything else (UI, modes, recorder, demod) is variant-blind.
```

Total: ~700 lines back-end vs ~500 (singleton-only) or ~600 (A+M-only).
**~30-40% extra**, not 2x, because the variant-specific code is narrow.

#### Code organization (proposed)

```
src/pioner/back/acquisition/
  __init__.py
  base.py                   # AIProvider abstract class
  persistent.py             # PersistentAIProvider (singleton-fixed)
  per_experiment.py         # PerExperimentAIProvider (A+MonitorMode)
  ring.py                   # Shared ring buffer with cursors
  recorder.py               # Shared DiskRecorder
  monitor_ao.py             # Shared MonitorAO helper

src/pioner/back/modes.py    # FastHeat/SlowMode/IsoMode talk to AIProvider
src/pioner/shared/settings.py   # Reads AcquisitionMode config
```

`AIProvider` interface (sketch):

```python
class AIProvider(ABC):
    @abstractmethod
    def on_connect(self) -> None: ...
    @abstractmethod
    def on_disconnect(self) -> None: ...
    @abstractmethod
    def arm_for_experiment(self, mode_name: str) -> None: ...
    @abstractmethod
    def end_of_experiment(self) -> None: ...

    # Shared (concrete in base):
    def peek(self, samples: int) -> np.ndarray: ...
    def read_new(self, consumer_id: str) -> np.ndarray: ...
```

Mode classes (`FastHeat.run()` etc.) call `ai_provider.arm_for_experiment(...)`
and `ai_provider.end_of_experiment(...)`. They never see which
implementation is active.

#### Config flag

```json
"Experiment settings": {
    "Acquisition": {
        "Mode": "persistent",
        "_comment": "persistent | per_experiment; persistent is the recommended default; per_experiment kept for A/B testing during the trial period"
    }
}
```

- **Read at Connect.** Switching the flag at runtime is not supported;
  it would require disconnecting and reconnecting the DAQ. Acceptable
  for testing because it's a deliberate "switch and reconnect" act.
- **Default if missing**: `persistent`. Fail-safe: a config without
  the flag gets the design we've documented as primary.
- **Not exposed in the operator UI.** Lives only in `config.user.json`.
  Switching requires editing the file manually -- prevents accidental
  flips during real runs.

#### What stays the same regardless of variant

Important so we don't re-litigate decisions every time we switch:

| Concern                                | Both variants                                                  |
|----------------------------------------|----------------------------------------------------------------|
| HDF5 file schema                       | Identical (data/, calibration, settings, metadata)             |
| Demodulation algorithm                 | Sliding-window FFT, 5 periods, stateless per tick              |
| AO program per mode                    | Identical (fast-heat profile, slow ramp+AC, iso modulated, calibration stages) |
| EXTTRIGGER handling                    | Identical at AO arm site                                       |
| Disk recorder lifecycle                | Dormant -> open at Arm -> drain -> close at experiment end     |
| UI live display cadence                | 100 ms slow-heat plot, 250 ms Values sidebar                   |
| FastHeat block-mode UX                 | Identical (still blocks, still returns full DataFrame)         |
| Operator's mental model                | Identical -- "Arm, wait or trigger, end"                       |

What differs is only **whether AI starts at Connect or at Arm**, and
**whether MonitorMode exists as a class**. Everything operator-facing
is the same.

#### Decision rubric -- how we pick the winner

Without numeric criteria up-front, the decision becomes "whichever
one feels better" which is not a decision. The trial period needs to
collect specific metrics, and the rubric below should be agreed
**before** the trial starts.

| Metric                                           | Target               | Measured by                              |
|--------------------------------------------------|----------------------|------------------------------------------|
| AI scan crashes / FIFO overruns per 8-hour run    | 0                    | log entries with `ULError.OVERRUN`       |
| Recording gaps detected in HDF5 files             | 0                    | metadata `samples_dropped` field          |
| Handoff failures (A+M only): pause/resume races   | <0.1% over 100 cycles | structured log "handoff_outcome"          |
| Trigger-to-first-recorded-sample latency          | <100 ms              | post-run analysis vs reference clock      |
| Sustained memory footprint over 8-hour session    | <500 MB              | OS process memory monitoring              |
| Operator perceived "stability" rating             | >= 8/10 over 10 runs | operator survey at end of each shift      |
| Setup time from "Open app" to "Ready to Arm"      | <30 s                | manual timing                             |

**Decision rule (consistency with operator priorities):**

1. If either variant fails any "= 0" criterion (crashes, gaps), it
   loses unconditionally.
2. If both pass crash/gap criteria, prefer the variant with **lower
   operational complexity** (fewer moving parts) -- this is
   singleton-fixed by design.
3. If singleton-fixed shows persistent-AI drift / memory issues over
   8 hours and A+M does not, A+M wins.
4. Operator stability rating is tie-breaker, not primary.

#### Telemetry requirements for the trial

Both variants must emit structured log events at INFO level:

- `acquisition.connect` -- start time, variant, AI params
- `acquisition.disconnect` -- end time, total samples acquired
- `acquisition.fifo_overrun` -- timestamp, scan index at failure
- `experiment.arm` -- mode, timestamp, EXTTRIGGER flag
- `experiment.trigger_detected` -- timestamp (only if EXTTRIGGER mode)
- `experiment.end` -- timestamp, samples recorded, file size
- `handoff.outcome` (A+M only) -- "ok" or "timeout" with elapsed ms
- `recorder.backpressure` -- if `read_new` returns chunk smaller than
  ring's worker output (i.e., we're falling behind)

Logs go to `logs/acquisition.YYYY-MM-DD.jsonl` for post-run analysis.
A small companion script generates the rubric metrics from the log
files at the end of the trial.

#### Deadline and retirement

The dual implementation is **temporary by design**. Hard schedule:

- Week 0: ship both variants behind the flag. Default is
  `persistent`. Operator notified that `per_experiment` is available
  for testing.
- Week 1-2: dedicated hardware soak in `persistent` mode, ~8 hours of
  continuous operation, collect metrics.
- Week 3-4: dedicated hardware soak in `per_experiment` mode, same
  duration. Collect metrics.
- Week 5: review against rubric, pick winner, **delete the loser's
  code** in the same week. Update [docs/live-streaming.md](live-streaming.md)
  to remove the variant-specific paths, update config schema to remove
  the flag.

If review is delayed past week 5: dual implementation slipping toward
"permanent fork" failure mode. Escalate or pick the default; do not
let it drift.

#### Risks specific to dual implementation

Beyond the cost overhead documented above:

- **Bit-rot.** Months later, fixes go to one variant but not the
  other. Mitigated by deadline above.
- **Test parametrization burden.** ~10-15 tests need to be
  parametrized over both providers. pytest fixtures support this
  cleanly, but test runs take longer.
- **CI cost.** Running the full test suite in two configurations
  doubles CI time (currently ~13 seconds, would become ~26).
  Acceptable.
- **Operator confusion if flag set wrong.** Mitigated by hiding the
  flag from UI; flipping requires editing `config.user.json` deliberately.
- **Documentation maintenance.** Both variants need accurate docs
  during the trial. After the trial, the loser's documentation
  becomes a postmortem entry (see [../postmortem/](../postmortem/)).

#### Recommendation on the dual-implementation question itself

This sub-section documents the option. **Whether to do it** is a
schedule + risk-appetite call, not a technical one:

- If we believe singleton-fixed is the right design and hardware is
  unlikely to surprise us: build singleton-fixed only, treat §13 as
  insurance.
- If hardware behavior on long continuous scans is the dominant
  uncertainty and we have schedule slack: dual is worth it for the
  empirical validation.

My honest take is the former (singleton-fixed only, §13 as fallback),
**unless the operator wants to invest in formal A/B validation before
committing**. The dual-implementation infrastructure adds ~2 weeks of
work for what is ultimately a single decision; that's a lot of
overhead unless the stakes (long-running production deployment) are
high enough to justify it.

### When to revisit alternatives

Concrete signals that would push us off the current design:

| Symptom in hardware/soak                                          | Probable cause                                                  | Switch to                                                                  |
|-------------------------------------------------------------------|-----------------------------------------------------------------|-----------------------------------------------------------------------------|
| Persistent AI scan dies / leaks memory after several hours        | uldaq driver / firmware limitation on long CONTINUOUS scans     | Variant A (per-mode short scans) or A+MonitorMode (with bounded duration)  |
| Need different sample rates per mode for new science              | Hardware capabilities can't be averaged across modes            | Variant A or A+MonitorMode                                                  |
| Operator demands simultaneous Tango + local GUI access            | Out of scope today, deferred                                    | Add owner-tagged subscription to current design (closer to B), or run Tango against a separate ExperimentManager that doesn't hold persistent AI |
| Recorder backpressure stalls (FIFO overrun) when SSD writes lag   | Disk write rate insufficient for sustained 1 MB/s + bursts      | Increase ring buffer to >10 s, or pre-allocate HDF5 file space             |
| State leakage between long sessions                               | ExperimentManager accumulates state across modes                | Variant A: each mode gets a fresh ExperimentManager (current Tango pattern) |

---

## 14. Glossary

- **AI session** -- an active analog-input scan on the DAQ.
  `ai_handler.scan(...)` starts; `ai_handler.stop()` ends.
- **AcquisitionStream / persistent AI** -- the AI session that, in the
  finalised design, runs from Connect to Disconnect without stopping.
- **Ring buffer** -- bounded in-RAM deque inside `ExperimentManager`
  that `_ring_loop` writes to and consumers read from. Lossy: ~2 s
  capacity, oldest samples are overwritten under backpressure.
- **Sliding-window demod** -- on each UI tick, take the most recent N
  samples from the ring buffer, run a fresh stateless FFT or lock-in
  on them, produce one (t, A, phi) point.
- **Disk recorder** -- background worker that, when active, drains the
  ring buffer via `read_new_ring_buffer` and writes to an HDF5 file.
  Dormant between experiments, active from Arm to experiment end.
- **MonitorAO** -- the AO state between experiments: typically zero
  base + AC modulation per config.json. Stopped at Arm, restarted at
  experiment end. Not a mode in `back/modes.py`, just an internal
  helper.
- **Arm** -- operator-controlled handshake before starting an
  experiment. Sets up AO scan (with EXTTRIGGER flag if external trigger
  used), starts disk recorder, raises Ready signal.
- **EXTTRIGGER mode** -- `ScanOption.EXTTRIGGER` on the AO scan; the
  scan is fully armed but doesn't start until a TTL edge on TTLTRG.
- **Pre-trigger baseline** -- AI samples recorded between Arm and
  trigger fire. Length = operator's choice, captured naturally by
  having the disk recorder active from Arm onwards.
- **Lossy / lossless** -- a ring buffer is lossy if older samples can
  be overwritten before being consumed. Our UI display ring is lossy
  (it's for display, not record). The disk recorder is lossless
  because it reads `read_new_ring_buffer` faster than the ring fills
  (1 MB/s producer vs >50 MB/s SSD consumer).
