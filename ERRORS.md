# ERRORS — chronological index of resolved incidents

Short, chronological log of serious or hard-won problems we hit, each linking
to its full write-up in `postmortem/`. Newest last. Add a one-line entry here
whenever a new postmortem lands.

Each `postmortem/<date>-slug.md` write-up follows: symptom, what was assumed
(often wrong), how the truth was established, what changed in code/docs,
lessons learned.

| Date | Problem (one line) | Write-up |
|------|--------------------|----------|
| 2026-05-23 | `ULError.OVERRUN` (FIFO overrun) on the legacy `CONTINUOUS` AI fast-heat path: a hardware-paced 20 kHz x N-channel producer outran a Python+HDF5 consumer (worse under VM USB pass-through). Fixed in the IR branch by a single-shot `DEFAULTIO` finite scan with a full-length host buffer. Mainline `finite_scan` uses a 1 s buffer + half-flip and is the same risk class (open: P1-30). | [postmortem/2026-05-23-fifo-overrun-continuous-ai.md](postmortem/2026-05-23-fifo-overrun-continuous-ai.md) |
| 2026-05-23 | "DIFFERENTIAL vs DEFAULTIO" confusion while debugging the overrun: an operator's "switched single-ended to default" was read as an AI **input-mode** flip, but USB-2637 has no differential mode — the real fix was the **scan-option** change (`CONTINUOUS` -> `DEFAULTIO`). A dead-code `AiInputMode.DIFFERENTIAL` fallback and several wrong doc facts were removed; `ai_device.py` now raises instead of falling back. | [postmortem/2026-05-23-differential-vs-defaultio.md](postmortem/2026-05-23-differential-vs-defaultio.md) |
| 2026-09-03 | Heater left powered after an exception mid-run (latent, found by review): `zero_ao` ran only on cooperative cancel / disconnect, so an unhandled error in the collect loop or a streaming run left the DAC latched at its last sample. Fixed with `try/finally` + `completed` flag in `finite_scan` and `_run_streaming` (zeroing before recorder teardown), plus an `atexit` backstop. | [postmortem/2026-09-03-heater-latch-on-abnormal-run-exit.md](postmortem/2026-09-03-heater-latch-on-abnormal-run-exit.md) |
| 2026-09-03 | "Check heater" reported a confident **"ok"** on a completely unpowered heater: the `1e-9` "powered" gate only guarded exact zero, so ADC-scale noise (even the mock's own 0.5 mV) produced a finite noise-over-noise `Rhtr` (median ~485, 3991/4000 "valid" samples). Gate replaced by the calibration field `Ihtr idle floor` (default 5e-4 V, proxy domain, bench-tunable); idle now yields NaN `Rhtr` -> verdict "unknown". | [postmortem/2026-09-03-heater-health-false-ok-from-idle-noise.md](postmortem/2026-09-03-heater-health-false-ok-from-idle-noise.md) |
