# PIONER: open-source core vs. proprietary nanocal split

> **Status: PLAN ONLY. Do not start refactoring.** This document records the
> verified design for separating PIONER into (1) a reusable, instrument-agnostic
> DAQ library that could be published to PyPI and (2) the proprietary
> nanocalorimeter code that stays private. Every coupling claim below was
> checked against the code on 2026-06-04 with the cited `file:line`.

## 1. Goal

Extract the "back" plumbing -- talk to an MCC USB DAQ over `uldaq`, the
pure-Python mock backend, channel / range / sample-rate configuration, AO/AI
scan orchestration, and the live-streaming acquisition providers -- into a
**generic open-source library** usable by any `uldaq`-based project. Keep the
nanocalorimeter-specific parts (chip calibration polynomials, the fast/slow/iso
experiment modes, heater/guard topology, AC-modulation + software lock-in,
safe-voltage limits) in the **proprietary** layer that depends on the library.

A small test front (CLI or minimal Qt) exercises the library on its own.

## 2. Verdict

**Feasible. Medium effort (~1 week part-time: ~2-3 days core refactor + tests).**
No architectural change -- it is code motion plus parameter injection. The
generic core is already import-clean; the coupling is concentrated in exactly
two files (`modes.py`, `mock_uldaq.py`) plus two `shared/` modules that must
move out (`channels.py`, `calibration.py`).

## 3. Evidence: the core is already decoupled

Verified -- these modules import **no** nanocal code (no `calibration`,
`channels`, `modulation`, or `modes` imports):

- `back/experiment_manager.py` -- imports only `shared.constants` (file paths)
  and `shared.settings.BackSettings` (generic DAQ params). Confirmed clean.
- `back/daq_device.py`, `back/ai_device.py`, `back/ao_device.py`,
  `back/ao_data_generators.py` -- pure `uldaq`/mock wrappers. Confirmed clean.
- `back/acquisition/{base,persistent,per_experiment,factory}.py` -- the AI
  provider interface and implementations. They import
  `experiment_manager.ExperimentManager` and call only generic lifecycle
  methods: `start_ring_buffer` / `stop_ring_buffer` / `snapshot_ring_buffer` /
  `peek_last_samples` / `read_new_samples`
  (`experiment_manager.py:273,328,336,362,386`). No nanocal leakage.

So the entire DAQ + acquisition spine moves with zero logic changes.

## 4. Where the coupling lives

### 4.1 `back/modes.py` -- the main offender (MIXED)

Imports the nanocal surface directly (`modes.py:38-59`):

```
from pioner.shared.calibration import Calibration            # :38
from pioner.shared.channels import (AD595_AI, DEFAULT_AI_CHANNELS,
    HEATER_AO, HEATER_CURRENT_AI, UHTR_AI, UMOD_AI, UTPL_AI,
    channel_index, channel_key)                              # :39-49
from pioner.shared.modulation import (...)                   # :50
from pioner.shared.utils import temperature_to_voltage       # :59
```

What is nanocal-specific inside `modes.py`:

- `apply_calibration()` (~`modes.py:180-298`): polynomial post-processing keyed
  on channel meaning (`if AD595_AI in df.columns`, heater Thtr from ch0/ch5,
  Uref tiling). Pure nanocal.
- `_program_to_voltage()` (~`modes.py:149-174`): temperature->voltage via the
  chip `theater*` polynomial + `safe_voltage` clamp.
- AC modulation tied to the heater channel (`modulation_channel = HEATER_AO`).
- The generic kernel (`finite_scan` / `iso_scan` orchestration) is buried among
  the above but does not itself need calibration.

### 4.2 `back/mock_uldaq.py` -- MIXED

The `uldaq` stub is generic, but `_MockAiDevice._synthesise_sample()`
(`mock_uldaq.py:401-420`) hard-codes nanocal channel semantics:

```
if channel == 0:  return base_voltage / 1700.0 + noise   # heater current proxy
if channel == 5:  return base_voltage + noise            # heater voltage fb
if channel == 4 or channel == 1: ... 0.005 * base ...    # mock thermopile
if channel == 3:  return 0.25 + noise                    # AD595 ~25 C
```

The mock is reusable as a DAQ stub but currently emits nanocal-shaped data.

### 4.3 `shared/` modules that are nanocal but sit in `shared/`

- `shared/channels.py` -- the fixed 6-channel AI / 4-channel AO layout (heater
  on ch1, guard ch2, AD595 ch3, thermopile ch4, etc.). NANOCAL.
- `shared/calibration.py` -- chip polynomials (`utpl*`, `ttpl*`, `thtr*`,
  `theater*`, `ac*`, `rhtr`, `rghtr`, `safe_voltage`) + `HardwareCalibration`
  (AD595 correction, amp gains). NANOCAL.
- `shared/modulation.py` -- AC modulation + lock-in + FFT demod + AO-period
  integrity. Calorimetry-specific (useful generically, but conceptually nanocal).
- `shared/utils.py` -- MIXED: `is_int`, `is_int_or_raise`, `list_bitwise_or`,
  `Dict2Class` are generic; `voltage_to_temperature` / `temperature_to_voltage`
  (`utils.py:55-118`) take a `Calibration` and are nanocal.
- `shared/constants.py` -- MIXED: file-path / sample-rate constants are generic;
  the calibration-JSON field names are nanocal.
- `shared/settings.py` -- MIXED but already tolerant: it lazily imports
  `DaqParams`/`AiParams`/`AoParams` (`settings.py:20-27`) and parses generic DAQ
  params; it also reads nanocal modulation defaults. Generic DAQ parsing can be
  reused; nanocal field interpretation stays proprietary.

## 5. Proposed boundary

**GENERIC library** (working name `uldaq-lab` / `daqkit` -- *name TBD, user
decides*): zero nanocal imports, channel-agnostic, voltage in / voltage out as
raw numpy.

```
<libname>/
  daq_device.py          # DaqDeviceHandler, DaqParams
  ai_device.py           # AiDeviceHandler, AiParams
  ao_device.py           # AoDeviceHandler, AoParams
  ao_data_generators.py  # ScanDataGenerator
  experiment_manager.py  # ExperimentManager, ScanResult (1 s constraint lifted)
  mock_uldaq.py          # uldaq dispatcher + mock with pluggable data generator
  acquisition/{base,persistent,per_experiment,factory}.py
  util.py                # is_int, is_int_or_raise, list_bitwise_or, Dict2Class
```

**PROPRIETARY layer** (`pioner`, depends on the library):

```
pioner/
  nanocal/
    channels.py          # moved from shared/
    calibration.py       # moved from shared/
    modulation.py        # moved from shared/
    pipeline.py          # NEW: apply_calibration + _program_to_voltage (out of modes.py)
    convert.py           # voltage_to_temperature / temperature_to_voltage (out of utils.py)
  back/
    modes.py             # BaseMode/FastHeat/SlowMode/IsoMode, calibration-pipeline-injected
    device_controller.py # LocalDeviceController wires lib + nanocal
    nanocontrol_tango.py # unchanged
  front/                 # unchanged
  shared/settings.py     # generic DAQ parse from lib + nanocal field interpretation
  shared/constants.py    # nanocal field names; generic paths can import from lib or stay
```

## 6. The hard refactors (3 + 1)

1. **Extract the calibration pipeline out of `modes.py`** (hardest).
   Move `apply_calibration()` and `_program_to_voltage()` into
   `nanocal/pipeline.py` verbatim (no logic change). Make
   `BaseMode._build_profiles()` (`modes.py:358-364`) take a pluggable
   profile-builder strategy: the generic default passes voltages through
   unchanged; the nanocal modes inject `_program_to_voltage`. ~4-5 h.

2. **Parameterize the mock data generator.** Give `MockAiDevice` an optional
   `sample_fn(channel, t) -> float` callback (or a `NanocalMockAiDevice`
   subclass). Library tests use a null/random generator; nanocal supplies the
   thermopile/heater/AD595 synthesizer. ~2-3 h.

3. **Move `channels.py` + `calibration.py` to `nanocal/` and fix imports.**
   Main consumer is `modes.py`; also `fastheat.py`/`slow_mode.py`/`iso_mode.py`
   shims, `device_controller.py`, `debug.py`. Move `voltage_to_temperature` /
   `temperature_to_voltage` to `nanocal/convert.py` (or keep them accepting a
   `Calibration` arg). ~2-3 h.

4. **(Recommended, optional) Lift the 1-second buffer constraint.** Today the AI
   buffer is one second (`experiment_manager.py:480`,
   `total_samples_per_channel = sample_rate * seconds` at `:494`) and durations
   must be whole seconds (`modes.py:119` `total_ms % 1000`). A generic library
   should not impose `total_ms % 1000 == 0`; size the buffer to
   `ceil(seconds) * sample_rate` and trim the tail. Even reshape stays valid by
   rounding the half-buffer up. ~1-2 h. (Tracked in todo as the buffer-length
   item.)

## 7. Simple front to exercise the library

Minimal surface needed: connect -> set channels/rate -> start/stop AI stream ->
read samples -> set a static AO voltage / play an AO profile. The existing
`LocalDeviceController` + `front/scope_controls.py` already cover ~80% of this;
the only library-level gap is that `LocalDeviceController.arm()/run()` are
mode-wired (nanocal). For the library, expose `ExperimentManager` directly (it
already has `finite_scan`, `ao_set`, `ao_modulated`, `start_ring_buffer`,
`peek_last_samples`). A ~100-line CLI (or a stripped Qt scope tab) is enough for
a smoke/demo front.

## 8. Packaging & licensing nuances

- **Two distributions:** publish `<libname>` (permissive licence, e.g. MIT/BSD)
  to PyPI; keep `ppioner` private and add `<libname>` as a dependency. The
  current PyPI name is `ppioner` / import `pioner` -- unchanged.
- **`uldaq` dependency:** the library hard-depends on the `uldaq` Python
  bindings being importable for real hardware, but ships the mock so it is
  usable with no board (same pattern as today: `mock_uldaq.DAQ_AVAILABLE`).
  Keep the `[hardware]` extra for the real `uldaq`.
- **Settings format:** the library should read only the generic DAQ block
  (interface, connection, channels, range, sample rate, `HardwareTrigger`); the
  nanocal field interpretation (calibration, modulation) stays in `pioner`.
  Decide whether the library owns a minimal settings schema or just accepts a
  `DaqParams`/`AiParams`/`AoParams` object built by the caller.
- **Mock data contract:** document that the library mock emits zeros/noise by
  default; realistic chip signals are a nanocal plug-in.
- **Tests:** split the suite -- generic DAQ/acquisition/mock tests ship with the
  library; calibration/modulation/modes tests stay private. ~half the current
  100 tests are library-side (DAQ, mock, acquisition, settings parsing).

## 9. Risks / open questions

- **Profile-builder seam:** the cleanest cut is making `_build_profiles`
  pluggable; verify no mode reaches around it (FastHeat/SlowMode/IsoMode all go
  through `_build_profiles` today -- confirm before moving).
- **`shared/constants.py` split:** generic path constants vs nanocal field
  names -- decide whether the library re-exports paths or the app owns them.
- **Tango server** (`nanocontrol_tango.py`) stays proprietary; it is currently
  unverified anyway (persistent-AI incompatibility).
- **Naming + licence** of the public package -- user's call.
- **CI:** the library needs its own minimal CI (mock-only) so it can be released
  independently of the nanocal repo.

## 10. Phased plan (when approved -- not now)

1. Boundary proposal sign-off (this doc) + pick library name/licence.
2. Lift the 1-second constraint (isolated, low risk, also helps the app).
3. Parameterize the mock data generator.
4. Extract `apply_calibration` / `_program_to_voltage` -> `nanocal/pipeline.py`;
   make `_build_profiles` pluggable.
5. Move `channels.py` / `calibration.py` / converters into `nanocal/`.
6. Carve the generic modules into a sibling package in-repo (monorepo) first;
   verify zero nanocal imports with an import-linter rule.
7. Split the test suite; stand up library-only CI.
8. Only then extract to a separate repo / PyPI project if desired.

Do steps 1-5 behind the current API so the app keeps working at every commit;
the actual package extraction (6-8) is the last, reversible step.
