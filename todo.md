# PIONER — back-end TODO list

Stepwise, executable backlog of open work on the back-end (no front-end items).
Each item is self-contained: what to do, where, why, and how to verify. **P0**
items go first, **P3** is polish.

File references use the `path/to/file.py:line` format. Test command:
`PYTHONPATH=src .venv/bin/pytest -q`.

## Status

- `pytest tests/`: **48 passed** (mock backend, ~10 s).
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

### P0-3. `apply_calibration`: validate `Ihtr` / `Uhtr` dimensions with the physicist

**Where:** `src/pioner/back/modes.py:209-227`

**What:** `ih = ihtr0 + ihtr1 * df[0]` treats AI ch0 as a raw shunt voltage
(V), but later feeds `ih` into `Rhtr = ... / ih` as if it were amperes. With
the default identity calibration `ihtr1 = 1.0`, that is dimensionally "1 V"
and `Rhtr` ends up in `[Ω·V/A]`, not Ω. In production, `ihtr1` is presumably
`1/Rshunt ≈ 1/1700 ≈ 5.88e-4`, but no test pins this down.

**Action:**
1. Confirm with the physicist what `ihtr1` represents in production. If it
   really is `1/Rshunt`, the production `calibration.json` must set it to
   `≈5.88e-4`.
2. Add explicit dimension comments next to each line in `apply_calibration`
   (`# ih: amperes`, `# df[5]: millivolts`, …).
3. Add a unit test: feed synthetic `V_shunt = 1 mA × 1700 Ω = 1.7 V` and
   `V_heater_raw = …`, assert `Rhtr ≈ 1700 Ω` for a properly-set calibration.

**Do not** modify the default identity calibration — it is the test fallback.

### P0-4. IsoMode AO buffer is not seamless at the production f_mod = 37.5 Hz

**Where:** `src/pioner/back/modes.py` (`IsoMode._build_profiles`) and
`settings/settings.json` (default `Modulation.Frequency = 37.5`).

**What:** the iso AO buffer is sized to exactly 1 second (`n = sample_rate
= 20000`). With `f_mod = 37.5 Hz` that is `37.5` cycles in the buffer ->
the CONTINUOUS replay re-emits sample 0 with a phase offset of
`pi rad` (half a period), producing a square-wave-like edge at every
1 s wrap. Symptom: the chip drive contains 60 % spectral leakage outside
the `f_mod` bin, the recovered C_p amplitude is biased, and the FFT-
demodulated `temp-hr_fft` disagrees with the time-domain lock-in.

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

**Action:** confirm with the physicist whether (1) is acceptable; if not,
implement (2). Either way, follow up with a real-hardware verification
that `temp-hr_fft.fundamental.amplitude` matches the time-domain lock-in
within ~1 %.

### P0-5. AO/AI start skew — real-hardware validation pending

**Where:** `src/pioner/back/experiment_manager.py` (`finite_scan`),
`src/pioner/back/daq_device.py` (`DaqParams.hardware_trigger`,
`fire_software_trigger`).

**Status:** the trigger primitive is implemented and mock-tested (see
`tests/test_modes_e2e.py::test_fast_mode_with_hardware_trigger_runs_clean`).
Both AO and AI pre-arm with `ScanOption.EXTTRIGGER` when
`BackSettings.daq_params.hardware_trigger=True`, and a single
`fire_software_trigger` call releases them on a shared t=0. Default is
`False` so existing callers and mock tests are unaffected.

**Open:** real-hardware loopback validation. Drive a 1 kHz square wave on
AO ch1, read it back on AI ch1, find the leading edge — must be within 1
sample of t=0 with `hardware_trigger=True`. If the board does not respond
to `EXTTRIGGER` cleanly, fallback options are documented inline in
`finite_scan` (pacer-clock sharing or a per-host software offset trim).

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

**Verification:** existing 33 tests + a new unit test asserting that raw
integer-named columns are **not** modified before `df.drop`.

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

### P1-10. `AiDeviceHandler.__init__` mutates the shared `AiParams`

**Where:** `src/pioner/back/ai_device.py:59-60`

**What:** if `SINGLE_ENDED` is unsupported, the code switches to
`DIFFERENTIAL` by mutating `params.input_mode` on the shared object.
Sharing `AiParams` between two handlers (currently nobody does, but
nothing prevents it) would silently couple them.

**Action:** `self._params = copy.copy(params)` in the constructor, or keep
the override on a local `self._input_mode_override`.

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

### P2-9. Iso mode does not save its result to disk

**Where:** `src/pioner/back/iso_mode.py`

**What:** asymmetry — fast/slow → `exp_data.h5`; iso → nothing.

**Action:** after **P2-8**, route all three modes through the shared
exporter.

### P2-10. Remove or implement `FAST_HEAT_CUSTOM_FLAG`

**Where:** `src/pioner/back/fastheat.py:55-68`

**What:** the parameter is accepted, stored, but never read anywhere.

### P2-11. `AiDeviceHandler` test coverage

**Action:** add `tests/test_ai_device.py`:
- Buffer re-allocation on `samples_per_channel` change.
- `scan()` without `allocate_buffer` raises `ValueError`.
- `INPUT_MODE` fallback to `DIFFERENTIAL`.

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

---

## Suggested execution order

1. **P0-3** — needs a conversation with the physicist; do not touch
   calibration coefficients before that.
2. **P0-5** — real-hardware loopback validation of the new
   `hardware_trigger` path, when access to the production DAQ is
   available.
3. **P1-5** — small follow-up to P1-1; the `stop()` primitive is in
   place, just needs the legacy `do_ai=False` path rewired around it.
4. **P1-3, P1-4** — independent, do in parallel.
5. **P1-6 → P1-16** — two or three at a time.
6. **P2-\*** — code-quality round after P0/P1 close.
7. **P3-\*** — last, or piggy-back on each P0/P1 PR.

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
