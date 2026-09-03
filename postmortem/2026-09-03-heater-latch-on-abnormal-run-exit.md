# Heater left powered after an exception mid-run (heater latch)

**Date:** 2026-09-03 (found by code review on 2026-09-02; never observed on
hardware -- latent, mock-only development so far)
**Scope:** `back/experiment_manager.finite_scan` (fast + owned slow),
`back/device_controller._run_streaming` (streaming slow / finite-iso).
**Impact:** any unhandled exception during AI collection or during a
streaming run left every AO channel latched at its last commanded sample.
On a real chip that means the heater stays powered -- at up to the full
program voltage -- until the operator presses Off or disconnects.

---

## Symptom

None observed in practice (all development on the mock). The gap was found
during a systematic review of the abnormal-exit paths against the repo's own
heater-safety rule ("Heater must reach 0 V on Off / disconnect / abort").

## What was assumed (wrong)

The rule was believed fully enforced because `zero_ao` demonstrably ran on:

* cooperative cancel (`request_stop` -> collect loop breaks -> zero),
* iso-hold abort (`stop_run`),
* disconnect.

The exception path was assumed covered by the `with ExperimentManager` /
`finally` teardown.

## How the truth was established

Reading every teardown path end-to-end: `ExperimentManager.stop()` and
`stop_ao()` only call `scan_stop`, and the MCC DAC **holds its last sample
until reset** -- a fact the codebase itself documents in the `zero_ao`
docstring. So on an exception inside `_collect_finite_ai` (or anywhere in a
streaming `mode.run`), the scans were stopped but the DAC stayed latched:

* `finite_scan`: `zero_ao` ran only when `self._cancel.is_set()` -- an
  exception skipped it entirely;
* `_run_streaming`: `zero_ao` ran only when `self._stop_requested` -- same
  gap, and the zeroing also depended on `recorder.stop()` not raising first.

## What changed

* `finite_scan`: collection wrapped in `try/finally` with a `completed` flag;
  AO is zeroed on **any abnormal exit** -- cancel *or* exception. Normal
  completion still keeps the program's final sample on the DAC (by design;
  programs end at 0 V).
* `_run_streaming`: same `completed`-flag pattern; the heater is zeroed
  **before** `recorder.stop()`, so heater safety does not depend on file
  teardown succeeding (the recorder just captures the zeroed tail).
* Tests: `test_finite_scan_zeroes_ao_on_collect_exception`,
  `test_streaming_run_zeroes_heater_on_exception`.
* Docs: README safe-voltage bullet + CLAUDE.md heater-zero rule now name the
  abnormal-exit coverage. A best-effort `atexit` hook was added as a further
  backstop for process-exit paths (cannot cover SIGKILL / hard crashes).

## Lessons learned

* A safety invariant is only real if it is enforced in `finally` -- covering
  the happy path and the cooperative-cancel path is not "always".
* "Scan stopped" is not "safe state" on hardware with latching DACs; every
  stop-shaped call must be audited for what the actuator does *afterwards*.
* When a rule says "must always reach X", enumerate the abnormal exits
  (exception, deadline, driver stop, process exit) and test each one.
