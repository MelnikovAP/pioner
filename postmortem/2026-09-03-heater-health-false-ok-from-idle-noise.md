# Heater-health verdict computed from ADC noise on a cold heater (false "ok")

**Date:** 2026-09-03 (found by code review + empirical mock check on
2026-09-02/03; never observed on hardware)
**Scope:** `back/modes.heater_resistance` (idle guard),
`back/device_controller.heater_health_report` (P2-24 "Check heater"),
`_rhcorr_operating_point` (P1-33 auto-zero input).
**Impact:** with the heater completely unpowered, the "Check heater"
diagnostic returned a confident verdict instead of "unknown". Measured on the
mock's own synthetic noise: 3991/4000 samples passed the "powered" gate,
median proxy R ~= 485 (pure noise-over-noise) -> verdict **"ok"** with
`n_valid = 3991` and an empty reason -- i.e. a missing or disconnected heater
could be reported as healthy. The same too-low gate let noise-based `Rhtr`
into the R-correction operating point.

---

## Symptom

None reported by operators (mock-only development). Found by asking "what
does the health check do on a chip that is not driven at all?" and running
exactly that scenario.

## What was assumed (wrong)

The `|ih| > 1e-9` guard in `heater_resistance` was believed to implement
"Rhtr is NaN at idle" -- the docs said so, and `heater_health_report`'s
docstring promised "unknown" for an unpowered heater. `1e-9` was even
described in units of amperes in older docs, though `ih` is a voltage proxy.

## How the truth was established

Empirically, with the mock's own noise model (`_synthesise_sample`:
deterministic ~0.5 mV sine): built an idle AI window (AO = 0, channels 0/5 =
noise only) and ran it through `heater_resistance` +
`classify_heater_resistance`:

```
idle Rhtr: finite 3991/4000 samples, median = 485
verdict at idle: ok
```

`1e-9` guards only *exact* zero (divide-by-zero); any real ADC noise -- and
even the mock's synthetic noise -- sails through it, so `Rhtr = (U5-U0)/U0`
over noise produced finite, plausible-looking values.

## What changed

* The gate is now a **calibration field**: `Ihtr idle floor`
  (`Calibration.ih_idle_floor`), default `5e-4` V in the proxy domain -- just
  above the mock's 0.5 mV noise. Legacy calibration files without the field
  fall back to the default; the value is bench-tunable per rig (P2-24) and
  belongs in the per-chip config (P1-42).
* `heater_resistance` marks all samples at or below the floor NaN, so
  `heater_health_report` on a cold heater now returns `unknown` with the
  "heater not powered" reason, and the rhcorr operating point excludes
  noise samples via the same single source of truth.
* Test: `test_unknown_on_idle_noise` reproduces the exact noise scenario.
* Docs: README, CLAUDE.md, `docs/pipeline.md`, TODO P2-24 updated (the old
  "~1 nA" / `1e-9` claims removed).

## Lessons learned

* A numerical epsilon is not a physical threshold. A "signal present" gate
  must sit **above the noise floor** and be a calibrated, tunable quantity --
  not a magic constant chosen to avoid division by zero.
* Validate every diagnostic against the *no-signal* case explicitly; a check
  that only ever saw driven signals has never been tested at all.
* When a doc states a guard's units ("1e-9 A"), verify the units exist in the
  signal path; here `ih` was never amperes, which helped the wrong constant
  survive review.
