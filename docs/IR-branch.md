# README-IR.md — analysis of `pioner-IR-branch/`

Scope: the snapshot in [pioner-IR-branch/](../pioner-IR-branch/) is the parallel
"IR" fork of the chip nanocalorimeter app. Nothing in here is wired into the
mainline `src/pioner/...` package; treat it as an independent code drop and
cherry-pick only what is named below. Filesystem reference is given from the
repo root.

---

## 1. Layout at a glance

| IR path                                            | Role                                                   | Mainline analogue                              |
|----------------------------------------------------|--------------------------------------------------------|------------------------------------------------|
| [pioner-IR-branch/runUI.py](../pioner-IR-branch/runUI.py) / [pioner_app/entrypoints/runUI.py](../pioner-IR-branch/pioner_app/entrypoints/runUI.py) | Qt entry point (silx + PyQt5)                          | [src/pioner/runUI.py](../src/pioner/runUI.py)     |
| [pioner_app/entrypoints/runEvaluation.py](../pioner-IR-branch/pioner_app/entrypoints/runEvaluation.py) | Standalone post-processing window                      | (none)                                         |
| [pioner_app/core/](../pioner-IR-branch/pioner_app/core/) | `settings`, `calibration`, `basemath`, `experiment_manager`, `constants`, `utils` | [src/pioner/shared/](../src/pioner/shared/) + [src/pioner/back/experiment_manager.py](../src/pioner/back/experiment_manager.py) |
| [pioner_app/hardware/](../pioner-IR-branch/pioner_app/hardware/) | `daq_controller` (Qt singleton), `ai_device`, `ao_device`, `fake_daq` | [src/pioner/back/ai_device.py](../src/pioner/back/ai_device.py) / [ao_device.py](../src/pioner/back/ao_device.py) / [daq_device.py](../src/pioner/back/daq_device.py) / [mock_uldaq.py](../src/pioner/back/mock_uldaq.py) |
| [pioner_app/backends/](../pioner-IR-branch/pioner_app/backends/) | Transport-abstraction factory: `direct` (uldaq) or `tango` | [src/pioner/back/nanocontrol_tango.py](../src/pioner/back/nanocontrol_tango.py) (tango server only) |
| [pioner_app/ui/](../pioner-IR-branch/pioner_app/ui/) | `mainWindow`, `mainWindowUi`, `h_windows`, `calibration_wizard`, `localization` | [src/pioner/front/](../src/pioner/front/)         |
| [pioner_app/ui/widgets/](../pioner-IR-branch/pioner_app/ui/widgets/) | All mode-specific UI panels                            | [src/pioner/front/...Widget.py](../src/pioner/front/) |

Sizes: IR branch is 41 .py files / ~13.5 kLoC vs mainline 34 .py files / ~8.4
kLoC. The bulk of the extra mass is UI (calibration wizard, modulation widget,
profile editor, three post-processing widgets).

---

## 2. Top-level workflow (when launched via `runUI.py`)

1. **Boot** — [runUI.py](../pioner-IR-branch/runUI.py) creates a `QApplication`,
   picks UI language ([localization.py](../pioner-IR-branch/pioner_app/ui/localization.py)),
   instantiates `mainWindow`. The experiment box and tab widget are initially
   disabled until the user hits "Connect".

2. **Connect** ([mainWindow.sysOnButtonPressed](../pioner-IR-branch/pioner_app/ui/mainWindow.py#L117)):
   - Reads `direct` vs `tango` from radio buttons → `DAQController.set_connection_mode`.
   - `DAQController.connect()` calls `create_hardware_backend(mode)`
     ([backends/factory.py](../pioner-IR-branch/pioner_app/backends/factory.py)),
     which returns `UldaqHardwareBackend` (functional) or `TangoHardwareBackend`
     (**stub: `connect()` always raises `NotImplementedError`**).
   - Builds an `ExperimentManager` and applies the input-gain panel state
     (per-channel range + auto-gain) by loading a uldaq AI queue
     (`a_in_load_queue`).
   - Switches the main tab to "Signals" and starts continuous AI acquisition.

3. **Continuous AI ring** — `DAQController.start_acquisition` →
   `ExperimentManager.start_continuous` → `AIDevice.start_scan_continious`. A
   single `points_per_channel` buffer is allocated; reads use
   `read_continuous` / `peek_continuous` with modulo wrap-around. Owner string
   ("signals", "values", "slow_heating", ...) prevents widgets from stomping on
   each other when they all want live data.

4. **Per-mode panels** under `mainTabWidget`:
   - **Signals** ([SignalsWidget](../pioner-IR-branch/pioner_app/ui/widgets/signalswidget.py)) — raw 6-channel scope view.
   - **Modulation / Slow heat** ([SlowHeatingWidget](../pioner-IR-branch/pioner_app/ui/widgets/modulationWidget.py#L168)) — see §4.
   - **Set Profile / Fast heat** ([ProfileWidget](../pioner-IR-branch/pioner_app/ui/widgets/exp_widget.py#L317)) — see §4.
   - **Result / Post-proc** ([procFastHeatWidget](../pioner-IR-branch/pioner_app/ui/widgets/procFastHeatWidget.py), [SimpleProcessWidget](../pioner-IR-branch/pioner_app/ui/widgets/simpleProcessWidget.py), [UniversalResultsWidget](../pioner-IR-branch/pioner_app/ui/widgets/universalResultsWidget.py), [EvaluationWidget](../pioner-IR-branch/pioner_app/ui/widgets/evaluationWidget.py)).
   - **Calibration wizard** ([calibration_wizard.py](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py)) — multi-stage interactive wizard (setup → live run → cursor on graph → polynomial fit → write to Calibration).

5. **"Values" sidebar** — a 250 ms `QTimer` in `mainWindow.update_values_widget`
   peeks the AI ring buffer and feeds it to
   `DataProcessor.analyze_slow_heating_chunk` for a lock-in snapshot
   (Ihtr / Rhtr / Thtr / Thtrd / Taux / Ttpl / amp / phase / power), plus
   per-channel auto-gain re-arming.

---

## 3. Core data flow (back-end)

```
DAQController (Qt singleton)            <-- mainWindow / widgets
  |
  +-- HardwareBackend (factory)          --> {Uldaq, Tango}
  +-- ExperimentManager
        +-- AIDevice (uldaq AI queue, per-ch gains, auto-gain)
        +-- AODevice (finite or CONTINUOUS scan; static a_out for held values)
        +-- AOGenerator       (fast-heat profile builder)
        +-- AOStreamSHGenerator (slow-heat ramp + F/A/P-ramped sine)
        +-- DataProcessor / lockin / fft_lockin / calcaf_lockin
```

[Calibration](../pioner-IR-branch/pioner_app/core/calibration.py) holds the same
coefficient set as mainline (`utpl0, ttpl0/1, thtr0/1/2/corr, thtrd*, uhtr0/1,
ihtr0/1, theater0/1/2, ac0..3, rhtr, rghtr, safe_voltage`) plus
`apply_fh_cal(raw_data)` that converts a raw 6-channel frame to
`(temp, temp_hr, Ihtr, Thtr, Taux)`. Same intent as mainline
`back.modes.apply_calibration`; differences in §6.

---

## 4. Modes — what exists per mode

### 4.1 Modulation only (AC drive, no ramp, no demod)

- **Entry**: `mainWindow.apply_modulation_params` → `DAQController.start_modulation(freq, amp, offset)` ([daq_controller.py:189](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L189)).
- **Algorithm**: build one period of `current_mA = offset + amp*sin(...)` at a
  rate picked so that `samples_per_period ∈ [256, 2048]`, convert to volts via
  `_heater_current_to_voltage` (uses `ihtr0/ihtr1` of the active calibration —
  i.e. the user-facing modulation amplitude is in **mA**, not volts), push to
  `AODevice.start_single_channel_wave(..., continuous=True)`.
- **Stop**: `stop_modulation` → `reset_ao_outputs(ao0=0.1, ao1=0.0)`.
- **Lock-in**: not on the modulation panel itself; the "Values" sidebar in
  `mainWindow` runs `analyze_slow_heating_chunk` against the live AI ring and
  produces a real-time amp/phase/Ihtr/Rhtr/Thtr/Taux snapshot, refreshed every
  250 ms.

> Behavioural difference vs mainline: there is no equivalent "AC-only drive
> with continuous lock-in readout" in `src/pioner` — mainline `IsoMode` uses
> CONTINUOUS replay too but ties it to a fixed `programs` shape and a
> dedicated finite measurement window.

### 4.2 Slow heat (ramp + AC modulation + lock-in)

- **Entry**: `SlowHeatingWidget.start_SH_exp` → `DAQController.start_slow_heating(freq, amp, offset, mode, start, end, rate_per_min, hold_final, demod_periods, modulation_ramps, point_interval_sec)` ([daq_controller.py:442](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L442)).
- **AO path** (worker thread):
  - `duration_sec = |end - start| / |rate_per_min| * 60`.
  - AO sample rate is **independent of AI**: picked from
    `samples_per_period ∈ [32, 256]`, capped at 8M total samples.
  - If no F/A/P modulation ramps are enabled, the AC is just `offset +
    amp*sin(...)` tiled over the full duration. Otherwise an
    `AOStreamSHGenerator` ([ao_device.py:260](../pioner-IR-branch/pioner_app/hardware/ao_device.py#L260))
    generates AC chunk-by-chunk while linearly interpolating
    frequency / amplitude / phase through `ramp_steps` discrete steps.
    `x2_mode` flips the demod target to `2*f`.
  - DC ramp on **ch1**: `start_value + dir * rate/60 * t`, clipped to
    `end_value`; if `mode == "temperature"` it is converted to volts via
    `basemath.temperature_to_voltage` and **then clipped to `safe_voltage`**.
  - Both channels are **pre-padded with one `min_point_interval_sec` block of
    zeros** so the AI demod gets a clean zero-baseline before the experiment
    starts. Then `ao.allocate_buffer + fill_buffer + start_scan` (finite).
- **AI path**: separate CONTINUOUS scan via `start_acquisition(owner="slow_heating", points_per_channel=ai_buffer)`. UI widget polls every 100 ms (`update_loop`), feeds chunks to `DataProcessor.analyze_slow_heating_chunk`, which:
  - Slices a window of exactly `requested_periods` integer-cycle periods
    (drops the first period to avoid filter transients).
  - Scales raw AI to engineering units (Umod /121, Utpl /11, Uhtr *1000) and
    derives Ihtr, Uabs, Ttpl, Thtr, Thtrd (RMS-based), Taux (AD595 + low-T
    polynomial), Power.
  - Picks the demodulator from a UI combo: **Lock-in** (`calcaf_lockin`)
    or **FFT** (`fft_lockin`). With a calibration loaded, the demodulated
    signal is `temp_hr_trace` (so the amplitude is `dT` in °C); without
    calibration it is `Umod_mV`.
- Stop: `stop_slow_heating` joins the AO thread, stops both scans, returns AO
  to the baseline.

### 4.3 Fast heat (paced finite AO+AI)

- **Entry**: `ProfileWidget` (segment table editor with V/T toggle, ramp /
  isotherm / sine segments) → `arm_profile` builds a profile dict and submits
  it to `DAQController.run_fast_heat_profile`.
- **Profile schema** (in-memory dict, identical on disk):
  ```json
  {
    "channels": {
      "0": [...],
      "1": [{"type":"ramp",     "duration":ms, "start":V, "stop":V},
            {"type":"isotherm", "duration":ms, "value":V},
            {"type":"sine",     "duration":ms, "frequency":Hz, "amplitude":V, "offset":V}],
      "2": [...]
    },
    "post_hold": {"enabled": true, "duration": ms, "channels": {"0": V, "1": V}}
  }
  ```
- **Runner**: `ExperimentManager.build_fast_heat_signals` materialises every
  step on the AO sample grid at `settings.sample_rate`. `_run_finite_profile`
  allocates AO+AI of matching length, then:
  1. `ai.start_scan(DEFAULTIO)`
  2. `ao.start_scan(DEFAULTIO)`
  3. Polls `ai.get_progress()` until `ScanStatus.IDLE`, emits `progress_cb`.
  4. Stops both, reads `ai.buffer`, reshapes to `(N, channels)`.
- **Post-processing**: `mainWindow.on_experiment_finished` →
  `DataProcessor.process_fast_heat` (applies calibration → engineering units +
  `Uref` ref trace) → `DataProcessor.save` to HDF5 (groups `data`,
  `calibration`, `settings`).
- **Result tab**: `resultsDataWidget` shows the saved trace next to the input
  profile segments.

> Same AI-before-AO ordering caveat as mainline's
> [TODO.md](../TODO.md) P0-5. Both branches reproduce the historical skew.

### 4.4 Iso (held setpoint + AC modulation + lock-in/FFT)

**Not present as a first-class mode.** What overlaps with our `IsoMode`:

- The Modulation panel above does CONTINUOUS AO replay of one AC period, which
  is the same drive primitive `back.modes.IsoMode._build_profiles` produces.
  But:
  - **No DC base voltage** on ch1 — modulation is fed directly to ch0
    (heater), no companion held setpoint.
  - **No ring buffer + post-run lock-in/FFT capture** — analysis happens
    only in the live "Values" sidebar (snapshot per 250 ms).
  - **No AO period integrity check** — the IR branch does not have anything
    analogous to mainline `check_ao_period_integrity`. If the user picks a
    frequency that does not divide the AO buffer length evenly, the
    CONTINUOUS replay will inject phase jumps every wrap and the lock-in
    output will be biased. This is silent in the IR branch.
  - **No 2f/3f harmonic decomposition** (apart from `x2_mode` which only
    rescales the demodulator's reference, not a multi-harmonic FFT).
- There is a half-finished `ExperimentManager.start_ao_continuous_mod`
  ([experiment_manager.py:282](../pioner-IR-branch/pioner_app/core/experiment_manager.py#L282))
  that builds a tiled AC drive and starts a CONTINUOUS AO scan, but it is
  not wired to any widget.

> If iso behaviour is needed in this fork, it would have to be either added
> as a new mode in the same shape as `SlowHeatingWidget` (held DC + AC +
> ring-buffer demod) or imported from mainline `back/modes.py::IsoMode`.

---

## 5. Demodulator zoo

[basemath.py](../pioner-IR-branch/pioner_app/core/basemath.py) ships **three**
implementations:

| Function           | Algorithm                                                   | Used by                                |
|--------------------|-------------------------------------------------------------|----------------------------------------|
| `lockin`           | Plain sin/cos multiply + simple `np.mean` (no LP filter)    | Not called from production paths       |
| `fft_lockin`       | Hanning-windowed `rfft`, nearest-bin amplitude/phase, coherent-gain correction | "FFT" choice in `analyze_slow_heating_chunk` |
| `calcaf_lockin`    | Port of the legacy C++ nanocal cross-correlation: builds a 1000-sample cross-correlation against the AI ref, runs a Levenberg-style iterative fit (50 iters) for amplitude/phase/offset, supports `modulation_amp` scaling, `x2_mode` (square the ref → demodulate at 2f), and a user-supplied `addphase` offset | "Lock-in" choice (default) in slow-heat panel + Values sidebar |

`calcaf_lockin` is the load-bearing one in this branch. The double `O(period
* xperiod)` loops at lines 93–116 and the iterative fit at 137–169 are pure
Python — fine for the slow-heat point cadence (~1 point/sec), but it will
choke on per-sample demod over a full scan. Mainline equivalents are
`shared.modulation.lockin_demodulate` (scipy `sosfiltfilt`, per-sample) and
`shared.modulation.fft_demodulate` (integer-cycle window, multi-harmonic
`FFTDemodResult`).

---

## 6. Comparison against mainline `src/pioner` (per mode)

### 6.1 What IR has that mainline does not

| Item                                                                                                                                       | Where in IR                                                                                            | Why it's useful                                                                                              |
|--------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| Per-channel AI input-range queue + auto-gain (uldaq `a_in_load_queue` + `AiQueueElement`)                                                  | [ai_device.py:159](../pioner-IR-branch/pioner_app/hardware/ai_device.py#L159), [_maybe_apply_autogain](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L169) | We never set per-channel ranges; we use one global `RangeId`. AI noise floor on Uhtr/Uref is wasted.         |
| `InputGainsPanel` widget (vertical sliders + auto-gain checkboxes, persisted in `config.user.json`)                                        | [input_gains_panel.py](../pioner-IR-branch/pioner_app/ui/widgets/input_gains_panel.py)                    | Natural front-end for the above.                                                                             |
| `HardwareBackend` factory (direct/tango) with a clean ABC contract                                                                         | [backends/base.py](../pioner-IR-branch/pioner_app/backends/base.py), [factory.py](../pioner-IR-branch/pioner_app/backends/factory.py) | We hardcode the direct-uldaq path; tango lives only on the server side.                                      |
| `DAQController` as a Qt singleton emitting `progress_changed` / `input_gains_changed`, with owner-tagged acquisition slots                 | [daq_controller.py](../pioner-IR-branch/pioner_app/hardware/daq_controller.py)                            | Multi-widget read coordination (signals/values/slow-heat all share one AI ring).                             |
| `AOStreamSHGenerator` — modulation parameter ramps (freq/amp/phase) during a slow-heat scan, with `ramp_steps` discrete steps              | [ao_device.py:260](../pioner-IR-branch/pioner_app/hardware/ao_device.py#L260)                             | Mainline has no F/A/P ramp during slow mode.                                                                 |
| `x2_mode` (demod at 2f via squared reference)                                                                                              | [calcaf_lockin](../pioner-IR-branch/pioner_app/core/basemath.py#L48)                                      | Useful as a cheap sanity check on heater nonlinearity. Mainline `fft_demodulate` already gets 2f/3f, so this is mostly redundant if you migrate to FFT. |
| `CalibrationWizard` — multi-dialog interactive procedure (setup table of reference points → live run → cursor pick on graph → polynomial fit → write coefficients to `Calibration`) | [calibration_wizard.py](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py)                          | We have no GUI calibration workflow.                                                                         |
| Profile editor with copy/cut/paste segments, V↔T toggle that re-converts table contents, per-segment rate labels on the plot               | [exp_widget.py](../pioner-IR-branch/pioner_app/ui/widgets/exp_widget.py)                                  | Better fast-heat UX than current `SetProg_widget`.                                                           |
| `post_hold` block in the fast-heat profile schema (holds a specified voltage per channel after the program completes)                      | [experiment_manager.py:404](../pioner-IR-branch/pioner_app/core/experiment_manager.py#L404)               | Mainline has no equivalent — useful to avoid relays clicking back to 0 V at the end of a profile.           |
| HDF5 averaging of multiple fast-heat scans (`average_exp_data` + structure check)                                                          | [procFastHeatWidget.py:414](../pioner-IR-branch/pioner_app/ui/widgets/procFastHeatWidget.py#L414)         | Standard "average N runs" workflow.                                                                          |
| `procFastHeatWidget` — heat-exchange calibration / power calculation from sample vs reference data                                          | [procFastHeatWidget.py](../pioner-IR-branch/pioner_app/ui/widgets/procFastHeatWidget.py)                  | The physical post-processing step we currently leave to the user's scripts.                                  |
| `SimpleProcessWidget` / `UniversalResultsWidget` / `EvaluationWidget` — generic file → fit / smooth / peak-find / area-integrate          | [simpleProcessWidget.py](../pioner-IR-branch/pioner_app/ui/widgets/simpleProcessWidget.py), [universalResultsWidget.py](../pioner-IR-branch/pioner_app/ui/widgets/universalResultsWidget.py), [evaluationWidget.py](../pioner-IR-branch/pioner_app/ui/widgets/evaluationWidget.py) | Reusable Qt / silx scaffolding for post-run analysis.                                                        |
| Live "Values" sidebar (`mainWindow.update_values_widget`) — running snapshot of Ihtr/Rhtr/Thtr/Thtrd/Ttpl/Taux/amp/phase/power + `T_error` and `phase_offset` zero buttons | [mainWindow.py:441](../pioner-IR-branch/pioner_app/ui/mainWindow.py#L441)                                 | Operator-facing readout that mainline lacks.                                                                 |
| Localization layer (en/ru) + `apply_language(widget)`                                                                                      | [localization.py](../pioner-IR-branch/pioner_app/ui/localization.py)                                      | Optional, but nice.                                                                                          |
| User-config layering: `config.json` (default) ← `config.user.json` (overrides), with `_deep_update`                                        | [settings.py](../pioner-IR-branch/pioner_app/core/settings.py)                                            | We currently read a single settings file.                                                                    |

### 6.2 What mainline has that IR does not

| Item                                                                                                       | Mainline location                                                              | Status in IR                                                                                                   |
|------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| `IsoMode` (held DC + AC + ring buffer + post-run FFT/lock-in, with multi-harmonic 1f/2f/3f decomposition)  | [back/modes.py:483](../src/pioner/back/modes.py#L483), [back/iso_mode.py](../src/pioner/back/iso_mode.py) | Absent.                                                                                                        |
| `check_ao_period_integrity` (verifies AO CONTINUOUS buffer wraps without a phase jump)                     | [shared/modulation.py:449](../src/pioner/shared/modulation.py#L449)               | Absent — CONTINUOUS modulation buffers are not validated.                                                      |
| Lock-in demod with proper LP filter (Butterworth `sosfiltfilt`)                                            | [lockin_demodulate](../src/pioner/shared/modulation.py#L121)                      | Absent — three competing demods, none have a proper LP.                                                        |
| `apply_calibration` with `HardwareCalibration` (`gain_utpl`, `gain_umod`, `ad595_low_correction`) externalised | [shared/calibration.py:78](../src/pioner/shared/calibration.py#L78)               | Constants 11.0 / 121.0 / AD595 polynomial are **hardcoded** inside `apply_fh_cal` and `analyze_slow_heating_chunk`. |
| `Calibration.write` (persists back to JSON)                                                                | [shared/calibration.py:233](../src/pioner/shared/calibration.py#L233)             | IR has `to_dict` / `to_file_dict` but the `write` method is commented out.                                     |
| `ChannelProgram` validation (time monotone, durations matching, `total_ms % 1000 == 0`, key-range check)   | [back/modes.py:78](../src/pioner/back/modes.py#L78)                               | Profile is consumed raw; no validation.                                                                        |
| `Rhtr = NaN` when current is below ~1 nA                                                                   | [back/modes.py:262](../src/pioner/back/modes.py#L262)                             | IR does mask `|Ih| < 1e-6` to NaN in `apply_fh_cal`; the parallel `analyze_slow_heating_chunk` returns `0.0` (silent zero, not NaN). |
| Test suite                                                                                                 | [tests/](../tests/)                                                               | None.                                                                                                          |
| `mock_uldaq` parity backend for development without DAQ hardware                                           | [back/mock_uldaq.py](../src/pioner/back/mock_uldaq.py)                            | `fake_daq.py` only mocks at the controller layer, not at the `uldaq` API layer — many AI/AO code paths still need the real `uldaq` import. |

### 6.3 Algorithmic differences worth flagging

| Topic                            | IR behaviour                                                                                                          | Mainline behaviour                                                                                                              |
|----------------------------------|-----------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| **Modulation domain**            | User enters AC **amplitude in mA**, converted to AO volts via `(I/1000 - ihtr0) / ihtr1`                              | User enters AC **amplitude in volts** directly on the heater AO. Two conventions; not interoperable without conscious conversion. |
| **`Rhtr` formula**               | `Rhtr = (Uhtr_mV - Uref_mV + uhtr0) * uhtr1 / Ih`. With identity calibration this yields mV/A = mΩ; under a hypothetical SI calibration `ihtr1 ≈ 1/Rshunt` (future P2-21; production uses identity, P0-3) with Uhtr_mV converted from V via `*1000`, the implicit assumption is `uhtr0` in mV. | Documented: keeps both numerator and denominator in V/A → Ω directly (see `back/modes.py:240`-280 comment). IR formula is consistent only if you remember `uhtr0` is in mV. |
| **AC modulation safety clip**    | Slow-heat AO worker clips DC ramp via `np.clip(ch1, …, safe_voltage)`; modulation buffer (`ch0`) is checked with `if np.any(np.abs(ch1) > safe): raise` — **no clipping**, hard error. Modulation-only `start_modulation` does not check at all. | `SlowMode/IsoMode._build_profiles` clip the modulated heater channel to `[0, safe_voltage]` (`np.clip(..., out=...)`) — never raises, just saturates. |
| **AC buffer integrity (iso)**    | Not checked. CONTINUOUS replay just runs whatever buffer was built.                                                   | `IsoMode._build_profiles` runs `check_ao_period_integrity` and logs a warning when `cycles_drift != 0`.                         |
| **Lock-in algorithm**            | `calcaf_lockin`: cross-correlation against the AO reference signal + iterative LM-style fit; works on any window length; phase offset `addphase` is a hand-tunable knob.                                       | `lockin_demodulate`: sin/cos demod + Butterworth LP; phase is wrt sin reference, no manual offset.                              |
| **FFT lock-in**                  | `fft_lockin`: Hanning window, single nearest bin, no integer-cycle slicing — leakage when `N*f/fs` is not integer.    | `fft_demodulate`: integer-cycle window via reduced-fraction logic, multi-harmonic (1f/2f/3f), exposes leakage fraction.         |
| **AI vs AO sample rates**        | Slow-heat: AO rate is chosen independently (`samples_per_period ∈ [32,256]`). AI rate stays at `settings.sample_rate`. They drift wrt each other. | All modes share one `BackSettings.ai_params.sample_rate / ao_params.sample_rate` (both equal in practice).                      |
| **AI buffer sizing**             | `points_per_channel` is computed per-widget request; modulo wrap-around inside `_read_continuous_window`.              | `ExperimentManager` sizes the AI buffer to exactly 1 s and half-flips it.                                                       |
| **Profile time grid**            | Each step's sample count = `round(duration_ms * sample_rate / 1000)`. No constraint that `total_ms % 1000 == 0`.       | Same now: the whole-second constraint was lifted; `finite_scan` trims to `round(sample_rate * total_s)`.                        |
| **AI/AO start order (fast-heat)**| `ai.start_scan()` then `ao.start_scan()` — same skew as mainline P0-5. | Same skew. Both are wrong.                                                                                                       |
| **Calibration JSON ext check**   | `if not os.path.splitext(path)[-1] != JSON_EXTENSION: raise` — **double-negation, always false** ([calibration.py:137](../pioner-IR-branch/pioner_app/core/calibration.py#L137)). Any file extension is accepted. | `_ensure_json_extension` does the right check.                                                                                  |

---

## 7. What's correct and reusable

Back-end:

- **`AIDevice` per-channel queue setup** ([ai_device.py:159](../pioner-IR-branch/pioner_app/hardware/ai_device.py#L159))
  + the surrounding range-position bookkeeping + `autogain_update_from_data`
  ([ai_device.py:268](../pioner-IR-branch/pioner_app/hardware/ai_device.py#L268)).
  This is the cleanest part of the back-end and ports straight into our
  `back/ai_device.py` if we want per-channel gains.
- **`HardwareBackend` factory pattern** (`backends/base.py`, `factory.py`,
  `uldaq_backend.py`). The Tango stub is unfinished, but the shape is right —
  worth adopting before we widen tango support.
- **`AOStreamSHGenerator`** ([ao_device.py:260](../pioner-IR-branch/pioner_app/hardware/ao_device.py#L260))
  for F/A/P-ramped modulation. The chunk-by-chunk API maps onto our existing
  `apply_modulation` if we want to extend `SlowMode` with parameter ramps.
- **`post_hold` block** in the fast-heat profile schema
  ([experiment_manager.py:404](../pioner-IR-branch/pioner_app/core/experiment_manager.py#L404))
  + the per-channel padding loop. ~10 lines, easy to graft onto our
  `ChannelProgram` builder.
- **DAQ ring-buffer modulo reader** ([experiment_manager.py:177](../pioner-IR-branch/pioner_app/core/experiment_manager.py#L177)).
  Compact and correct; can replace our half-buffer flip logic if we drop the
  "exactly one second" constraint.

Front-end:

- **`InputGainsPanel`** ([input_gains_panel.py](../pioner-IR-branch/pioner_app/ui/widgets/input_gains_panel.py)).
  Plug-and-play; only depends on `AIDevice.set_channel_gains`.
- **`ProfileWidget`** ([exp_widget.py:317](../pioner-IR-branch/pioner_app/ui/widgets/exp_widget.py#L317))
  — segment editor with V↔T conversion, segment clipboard, rate annotations
  on the plot, temperature-range pre-validation against `safe_voltage`. Better
  than our `SetProg_widget`. The dependency on the IR-specific `Calibration`
  is shallow (only `theaterconv` / `temperature_to_voltage`); easy to re-point
  at `pioner.shared.calibration`.
- **`procFastHeatWidget`** ([procFastHeatWidget.py](../pioner-IR-branch/pioner_app/ui/widgets/procFastHeatWidget.py))
  — averaging across runs + manual/auto heat-exchange correction (`empty_G`,
  `exp_P`). This is the physical post-processing we currently leave to scripts.
- **`SimpleProcessWidget`, `UniversalResultsWidget`, `EvaluationWidget`**
  — generic file → fit / smooth / peak-find UI bricks, depend only on silx +
  numpy. No PIONER-specific coupling.
- **`CalibrationWizard`** ([calibration_wizard.py](../pioner-IR-branch/pioner_app/ui/calibration_wizard.py))
  — biggest standalone win. The wizard wraps four dialogs
  (Setup → Run → Cursor → Polynomial fit / Heater fit / Ttpl fit) and writes
  back to `Calibration`. Pulling this in requires that the wizard's runtime
  (`DAQController.start_slow_heating` and the live AI stream) is in place;
  i.e. it's easier to port _after_ adding per-channel gains and the
  controller-singleton pattern.
- **`mainWindow.update_values_widget`** ([mainWindow.py:441](../pioner-IR-branch/pioner_app/ui/mainWindow.py#L441))
  — the live sidebar feed. Worth lifting wholesale once we have the demod
  stack unified.

Shared:

- The HDF5 layout (`data/...`, `calibration` (string), `settings` (string),
  `temp_volt_programs` would have to be added) is **almost** the same as
  mainline `save_run_to_h5` — close enough that the existing post-processors
  in `procFastHeatWidget` work against mainline files with only the dataset
  alias map (`_read_dataset_with_aliases`).

---

## 8. What's not OK / risks before reusing

Critical-to-fix when porting any of the back-end:

1. **Broken calibration extension check** — `if not os.path.splitext(path)[-1]
   != JSON_EXTENSION` always evaluates to `False`. Calibration files with any
   extension load silently. ([calibration.py:137](../pioner-IR-branch/pioner_app/core/calibration.py#L137))
2. **Dead-code-only `Calibration.unpack_data_numpy`** lives inside the class,
   contains an unreachable "save debug CSV" block after a `return` statement,
   and is referenced nowhere ([calibration.py:437](../pioner-IR-branch/pioner_app/core/calibration.py#L437)).
   Likely a stalled refactor. Delete on import, do not port.
3. **`Calibration.apply_fh_cal`** mixes `pandas.DataFrame` and `numpy`, mutates
   the input frame in place with `values[i] /= 1`, and the actually-used
   branch is after a giant commented-out block (lines 283–371). Two parallel
   formulas for `Rhtr` (lines 405-411 and 348-360 commented). When porting,
   pick the live formula, drop the rest.
4. **Unit conventions disagree across files**:
   - `analyze_slow_heating_chunk` does `Umod_mV = Umod / 121.0 * 1000.0` and
     `Uhtr_mV = Uhtr * 1000.0` (V → mV).
   - `apply_fh_cal` does `values[5] *= 1000.0` (V → mV) plus an explicit
     `Uref_mV = Uref * 1000.0`.
   - The Rhtr formula in `apply_fh_cal` is in mV/A; in
     `analyze_slow_heating_chunk` it is in V/A. Either form *can* be made
     correct, but the numerical scales of `uhtr0` and the `thtr*` polynomial
     have to match. The IR branch silently assumes both work; in practice
     `Rhtr` only matches mainline if you remember the mV convention.
5. **AC voltage clipping inconsistent** — see §6.3. Slow heat raises on AC
   overshoot, modulation-only path doesn't check.
6. **AI/AO start order** — same skew as mainline P0-5.
7. **Hardcoded data paths** in `core/constants.py`
   (`/home/nanocal/OLDPIONER/try/data`). Use `settings.data_path` instead.
8. **Singleton pattern of `DAQController`** is mutable global state — fine for
   a single GUI process but will fight unit tests and the existing tango
   server, both of which want a fresh `ExperimentManager` per call.
9. **No tests**. The IR branch was developed against live hardware; do not
   trust any numerical claim without re-deriving it.
10. **Encoding** — most docstrings are mojibake (cp1251 saved as utf-8). Will
    fail `ASCII-only` rule we have in CLAUDE.md if pulled in unchanged.

UI-specific risks:

- `mainWindow` and the widgets reach into each other via Python attributes
  (`self.window().freqInput`, `self.modulationWidget.periods_box`, etc.).
  Couples them tightly to `mainWindowUi.py`. Porting one widget means porting
  enough of `mainWindowUi` to satisfy the lookups, or refactoring to signals.
- `procFastHeatWidget.find_iso` is `pass` ([procFastHeatWidget.py:567](../pioner-IR-branch/pioner_app/ui/widgets/procFastHeatWidget.py#L567)),
  and the auto-correction path declares half its options "Still under
  development". Don't ship as-is.
- The Tango backend is a stub that raises `NotImplementedError`. Do not
  advertise tango support if you port `HardwareBackend` without finishing it.

---

## 9. Short recommendation for cherry-picking

Order of incorporation that minimises risk:

1. `HardwareBackend` factory (back, isolated).
2. Per-channel AI gains + `InputGainsPanel` (back+front, isolated).
3. `post_hold` for fast-heat profile (back, single function).
4. `ProfileWidget` (front, replaces `SetProg_widget`).
5. `mainWindow.update_values_widget`-style live readout (front, needs the
   live demod plumbing already in place — pick `shared.modulation` over
   `calcaf_lockin`).
6. `CalibrationWizard` (front, depends on 5).
7. `procFastHeatWidget` (front, decoupled from runtime; depends on HDF5
   schema alignment).
8. `AOStreamSHGenerator` modulation ramps (back) — only if slow-mode
   parameter ramps are actually a research requirement.

Things to **leave behind**: `calcaf_lockin` (replace with
`shared.modulation.lockin_demodulate` + `fft_demodulate`), the
`Calibration.apply_fh_cal` / `unpack_data_numpy` body (already implemented
correctly in mainline `back.modes.apply_calibration`), the broken JSON
extension check, the duplicated Tango stub.
