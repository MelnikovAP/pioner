# Hardware bring-up checklist (MCC USB-2637)

First-time bring-up of PIONER against a **real** MCC USB-2637, end-to-end
through the GUI on the in-process `LocalDeviceController` (no Tango). The code
preparation for hardware-mode testing has landed (status readout, settings-driven
`HardwareTrigger`, connect diagnostics, idle-Thtr guard, sample-count logging;
tracked as todo P1-28); this document is the operator checklist for the steps that
need the physical board.

> **HARD STOP per `CLAUDE.md`.** Steps 2-5 touch real hardware (anything that is
> not `mock_uldaq`). Each requires explicit in-session confirmation before
> running. Do not run them unattended, and never against the production chip
> without sign-off.
>
> **Heater safety.** "Off", the system disconnect button, and an iso-hold abort
> all drive the heater AO to 0 V (`ExperimentManager.zero_ao`), so a clean stop
> leaves the chip cold -- a scan-stop alone would latch the last setpoint on the
> DAC. This does NOT cover a GUI/process crash, so keep bring-up attended.

## Required configuration (verified on mock, 2026-06-03)

`settings/settings.json` and `src/pioner/settings/default_settings.json` agree
on the USB-2637 layout. Confirm before bring-up:

| Field                         | Required value            | Notes |
|-------------------------------|---------------------------|-------|
| `AcquisitionMode`             | `Persistent`              | live streaming path |
| `DAQ.InterfaceType`           | `[1]` (USB)               | bitwise-or list |
| `DAQ.ConnectionCode`          | `0`                       | first device |
| `DAQ.HardwareTrigger`         | `false` (until step 4)    | settings-driven (todo P0-5) |
| `AI.LowChannel` / `HighChannel` | `0` / `5`               | 6 channels streamed |
| `AI.InputMode`                | `2` (SINGLE_ENDED)        | USB-2637 is single-ended only |
| `AI.RangeId`                  | `5` (+/-10 V)             | |
| `AO.LowChannel` / `HighChannel` | `0` / `3`               | heater on ch1 |
| `AO.RangeId`                  | `5` (+/-10 V)             | |
| `Scan.SampleRate`             | `20000` (even)            | even rate required by the half-buffer flip |

## Steps

### 1. Install the driver + hardware extra (no board required yet)

- Install MCC's `libuldaq` shared library for your OS.
- `.venv/bin/pip install -e .[hardware]`.
- Confirm the real driver is picked up:
  `python -c "import uldaq; print('ok')"` and, on first import inside PIONER,
  the log line `Real uldaq detected, using actual DAQ hardware.`
  (`back/mock_uldaq.py`). If you instead see
  `uldaq not available (...); using mock backend.`, the import failed and PIONER
  is still on the mock -- fix the install before continuing.

### 2. Connect through the GUI  --  **HARD STOP**

- Plug in the board.
- `python -m pioner.runUI` (no `--mock`).
- Tick **run without hardware** (selects the in-process `LocalDeviceController`)
  and press **ON**.
- Confirm the new status line reads **`Connected: REAL DAQ (uldaq)`** (workstream
  A1). If it reads `MOCK DAQ (no hardware)`, the driver was not bound -- go back
  to step 1.
- If connect fails, the dialog now maps the common causes (no board / wrong model
  / missing `libuldaq`); act on the message (workstream A2).

### 3. Idle sanity  --  **HARD STOP**

- With the heater un-driven, the live Signals plot should tick and the **T htr**
  value should read `---` (workstream A3), not the ~-1071 sentinel. The live
  readout blanks Thtr while no drive is commanded; it shows a value only during
  an iso hold (when AO genuinely drives the heater). A finite Thtr at idle means
  the heater-driven gating is off.
- Watch the log for `Ring buffer worker stopped cleanly ...` on disconnect and
  for any `... possible underrun` WARNING (workstream B3) -- an underrun at idle
  points at sample-rate / USB-throughput trouble.

### 4. P0-5 trigger loopback  --  **HARD STOP** (when a trigger line is wired)

- Wire AO ch1 -> AI ch1 (and the trigger line / jumper per `experiment_manager.py`
  `finite_scan` inline notes -- USB-2637 has independent AO/AI pacers, so a
  physical jumper or external pulse is mandatory for clock-level sync).
- Drive a 1 kHz square wave on AO ch1, read it back on AI ch1.
- With `DAQ.HardwareTrigger: false`: measure the leading-edge skew between the
  commanded edge and the AI edge (baseline).
- Flip to `DAQ.HardwareTrigger: true` (no code edit needed -- settings-driven via
  `BackSettings.parse_daq_params`) and re-measure: the edge must land within 1
  sample of t=0. If `EXTTRIGGER` does not release cleanly, the fallback options
  (pacer-clock sharing / per-host software offset trim) are documented inline in
  `finite_scan`.

### 5. Short fast / slow / iso runs  --  **HARD STOP**

- Run a short program in each of `fast`, `slow`, `iso`.
- Any positive program duration is accepted (fractional seconds allowed; the
  AI frame is trimmed to `round(sample_rate * total_s)`).
- Cross-check the result against reference / mock-expected behaviour
  (`mock-verification.md`), watching the log for the new
  `AI finite scan complete: N / M samples per channel` line (workstream B3) --
  `N == M` means no short frame.
- Restore `data/exp_data.h5` afterwards if a run clobbered a reference scan.

## Slow off-ring soak (P1-17 step 4d) -- real hardware only

The slow mode now reads AI from the persistent ring instead of its own finite
scan (off-ring, P1-17 step 4c), and `DiskRecorder` streams the raw samples
straight to disk. Two things the mock **cannot** prove and that must be checked
on the real USB-2637 before trusting a long slow run:

1. **No FIFO `OVERRUN` over the full ramp duration.** The persistent ring runs
   CONTINUOUS at 2 kHz for the whole slow ramp (minutes to hours). Run the
   longest realistic slow ramp and confirm the log shows **no `OVERRUN`** and no
   `Ring buffer consumer ... fell behind` warnings (the `DiskRecorder` consumer
   must keep up; lower `poll_interval` if needed). At 2 kHz the drain margin is
   ~10x the 20 kHz that triggered the historical OVERRUN
   (`postmortem/2026-05-23-fifo-overrun-continuous-ai.md`), but verify it.
2. **Residual AO/AI start skew.** Off-ring alignment uses the software
   start-cursor (`DiskRecorder.mark_index`), not a hardware trigger, so there is
   a small skew (todo P0-5). Drive a known feature (e.g. a step in the ramp) and
   confirm it lands at the expected `Uref`/time within a few samples. If the
   skew matters, apply the per-host offset trim (P0-5).

Also confirm host RAM stays flat for a long run (streaming to disk works): watch
RSS during a multi-minute ramp -- it must not grow with the run length.

This is an operator bench procedure, **not** a CI test (the mock reproduces
neither overrun nor skew). Record the measured numbers here after the first run.

## Out of scope here

- **Tango path** (`TangoDeviceController`) -- unverified, repair tracked in todo
  P1-17. Bring-up uses Local only.
- **SI recalibration** of `ihtr1` (todo P2-21). The pinning test
  (`tests/test_calibration.py::test_default_calibration_pins_identity_constants`)
  guards the identity constants until that procedure exists.
- **Live-chip accuracy validation** (iso AO seamlessness at 37.5 Hz, lock-in edge
  transients, fast/slow live-stream-during-run) -- needs the board and is tracked
  separately in `TODO.md`.
