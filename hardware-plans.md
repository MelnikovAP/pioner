# Plan: High-priority work to enable HARDWARE-mode testing (back + front)

> **Verification status:** Every claim/line reference below was re-checked
> against the code on 2026-06-02 (second iteration). Corrections from the first
> draft are marked `[verified]` / `[corrected]`.

## Context

PIONER runs and is tested only on the mock `uldaq` backend. Goal: be **able to
test the app against a real MCC USB-2637**, end-to-end through the GUI, with
confidence. This is **code preparation only** -- no board is attached yet, so we
make code/UI/config ready so first bring-up is a checklist, not a debug session.

Decisions (with the user):
- **Path = Local in-process** (`LocalDeviceController` drives USB-2637 directly;
  no Tango). Tango is disabled (`nanocontrol_tango.py` raises under
  `AcquisitionMode='persistent'`) and its repair is **out of scope** here.
- **Make `hardware_trigger` configurable now** (settings-driven), so the P0-5
  AO/AI start-sync path turns on without a code edit.
- **No live-board steps** in execution; deliver a bring-up checklist for later.

Drivers (verified):
1. Backend selector is **misleading for hardware**: checkbox labeled *"run
   without hardware"* (`mainWindowUi.py:55`) but checking it selects
   `LocalDeviceController`, which uses the **real** board when present
   (`mainWindow.py:235-242`). The operator gets no signal real-vs-mock.
2. `hardware_trigger` is hardcoded `False` (`daq_device.py:32`) and **not**
   parsed from settings -- `parse_daq_params` (`settings.py:143-160`) reads only
   interface_type + connection_code. `[verified]` settings.json has no such field.

Folded-in user request: **pin calibration constants** (`ihtr0=0`, `ihtr1=1`,
etc.) with a regression test so they cannot silently drift before a recalibration
procedure exists.

`[verified]` settings layout: GUI loads `./settings/settings.json`
(`SETTINGS_FILE_REL_PATH`); tests/defaults load
`src/pioner/settings/default_settings.json` (`DEFAULT_SETTINGS_FILE_REL_PATH`).
Current values: InterfaceType=[1] (USB), ConnectionCode=0, AI 0-5 InputMode=2
RangeId=5, AO 0-3 RangeId=5, Sample rate=20000 (even), AcquisitionMode=persistent.

---

## Execution order (recommended)

Ordered by **dependency** and **risk** (isolated/safe first, UI last). Each step
is independently committable; run the per-step verification before moving on.

1. **C2 -- fix stale `ihtr1` docstring** (`shared/calibration.py:132-138`).
   Zero-risk doc edit, no behaviour change. Warm-up.
2. **C1 -- calibration-pinning test** + **C3 -- todo.md cross-link**. Pure
   safety net, no production code touched. *Verify:* new test passes; full suite
   still 94+.
3. **B1 -- `hardware_trigger` settings-driven** (constant + `parse_daq_params`
   + both JSONs) **+ round-trip unit test**. Backend config only; no GUI.
   *Verify:* `HardwareTrigger:true` -> `daq_params.hardware_trigger is True`;
   suite green; mock `debug.py` runs all three modes.
4. **B2 -- backend-kind property** (`is_mock` reading `mock_uldaq.DAQ_AVAILABLE`)
   on `LocalDeviceController`. **Dependency for A1** -- must land before the GUI
   status label. *Verify:* property returns True on mock.
5. **B3 -- sample-count observability** in `_collect_finite_ai` / `_ring_loop`.
   Backend logging only. *Verify:* suite green; counts logged in `debug.py`.
6. **A1 -- GUI status readout** (consumes B2) + **A2 -- connect diagnostics**
   + **A3 -- idle Thtr `---`**. Front-end last; do A1->A2->A3 in that order.
   *Verify:* offscreen GUI smoke -- status reads MOCK, idle Thtr shows `---`,
   fast/slow/iso run.
7. **D -- confirm `default_settings.json` agrees** + **E -- write
   `docs/hardware-bringup.md`**. Docs/config wrap-up.
8. **Final gate:** AST on all edited `.py`; `pyright` -> 0/0; full `pytest`;
   offscreen GUI smoke; restore `data/exp_data.h5` if a run clobbers it.

Rationale: C is a self-contained safety net with no coupling, so it lands first
and de-risks calibration drift immediately. B is backend-only and B2 must
precede A1 (the GUI reads the controller's mock/real flag). A (front-end) is the
highest-touch surface, so it goes after the backend it depends on is stable.
D/E are documentation. Nothing here requires the physical board; the live-board
steps stay in Workstream E as HARD STOPs.

---

## Workstream A -- Front-end: make real-hardware selectable & legible

- **A1. Backend/DAQ status readout.** After connect, show backend (Local) +
  whether the **real driver or mock** was selected. Truth source:
  `mock_uldaq.DAQ_AVAILABLE` `[verified mock_uldaq.py:45,49]`. Add a read-only
  property on `LocalDeviceController` (e.g. `is_mock`/`backend_description`
  reading `DAQ_AVAILABLE`), display in a GUI status label, and `logger.info` at
  connect.
  - Files: `back/device_controller.py`, `front/mainWindow.py`
    (`_after_connect`/`_connect_local`), `front/mainWindowUi.py` (one QLabel).
- **A2. Actionable connect diagnostics.** In `_connect_local`
  (`mainWindow.py:254-267`) distinguish/ message the real-DAQ failures instead
  of the generic text: no board (`RuntimeError("No DAQ devices found")`
  `[verified daq_device.py:60]`), missing `libuldaq` (`OSError`), and the
  SINGLE_ENDED validation error `[verified ai_device.py:73-81]`. Message-mapping
  only -- no logic change.
- **A3. Idle Thtr readout.** `[corrected]` The Values box shows **Thtr**
  (`thtrValueLabel` <- `last.get("Thtr")`) and dynamic temp-hr
  (`thtrdynValueLabel`) -- `[verified mainWindow.py:198-201]`; there is no Rhtr
  label. On a real idle chip Thtr shows the ~-1071 sentinel (todo P0-3,
  `todo.md:317-320`). In `_update_live_values` (`mainWindow.py:188`) show `---`
  for Thtr when no AO drive is active / value non-finite. Live-readout only;
  `apply_calibration` untouched.

---

## Workstream B -- Back-end: hardware-trigger config + connect observability

- **B1. Make `hardware_trigger` settings-driven.** Add `HardwareTrigger` bool
  (default `false`) to the `DAQ` block of **both** `settings/settings.json` and
  `src/pioner/settings/default_settings.json` `[corrected: two files, not one]`;
  add a field-name constant in `shared/constants.py` (beside
  `INTERFACE_TYPE_FIELD`/`CONNECTION_CODE_FIELD`, `[verified :37-38]`); parse it
  in `parse_daq_params` (`settings.py:143-160`) into
  `daq_params.hardware_trigger`. The EXTTRIGGER + `fire_software_trigger` path
  already exists (`experiment_manager.py:203-230,301-310`;
  `daq_device.py:139-155`) -- activates from config. AI-before-AO ordering is
  already correct (`experiment_manager.py:224-228`); leave it.
- **B2. Backend-kind property** (shared with A1).
- **B3. Sample-count observability.** In `_collect_finite_ai`, before
  `return df` (`[verified :575]`), log `collected` vs `total_samples_per_channel`
  (`[verified :494,518]`) at INFO, and on mismatch at WARNING; keep the existing
  deadline WARNING (`:520`). Same idea at `_ring_loop` tail (`:580`). On real
  hardware this makes a pacer underrun / flip-miss visible instead of a silently
  short frame. Observability only -- flip protocol untouched.

---

## Workstream C -- Pin calibration constants (user request)

- **C1. Regression test** that the bundled default calibration keeps its pinned
  identity values: `ihtr0=0.0`, `ihtr1=1.0`, `uhtr0=0.0`, `uhtr1=1.0` (and the
  other identity coeffs that must not move). Load via
  `Calibration().read(DEFAULT_CALIBRATION_FILE_REL_PATH)`, assert each using
  existing accessors (`[verified calibration.py:138-139,202-203]`). Add to
  `tests/test_calibration.py` (existing `[verified]`) or new
  `tests/test_calibration_pinning.py`.
- **C2. Fix stale docstring** `calibration.py:132-138` `[verified stale]` -- it
  says `ihtr1` is "shunt admittance in siemens (1/R_shunt)... production must set
  ihtr1 ~= 1/R_shunt so ih is in amperes", contradicting the physicist's
  confirmation this session (production is the dimensionless identity `ihtr1=1`;
  `ih` is a voltage-proxy). Align with the corrected comment in
  `modes.py:237-252`.
- **C3. todo.md entry** cross-linking the pinning test to P2-21 ("revisit
  constants when the SI recalibration procedure is defined"). Short cross-link,
  not a new P-section.

---

## Workstream D -- Config verification (code-prep)

`[verified]` current `settings/settings.json` already matches USB-2637
(InterfaceType USB, AI 0-5 InputMode=2 SINGLE_ENDED, AO 0-3, RangeId=5 = +/-10 V,
sample_rate=20000 even). Deliverable: record these as the required values in the
bring-up doc (E) and confirm `default_settings.json` agrees. No settings change
expected beyond B1's new field.

---

## Workstream E -- Hardware bring-up checklist (doc only)

New `docs/hardware-bringup.md` (steps run only when a board is attached -- each a
**HARD STOP / explicit-confirmation** per CLAUDE.md):
1. Install `libuldaq` + `pip install -e .[hardware]`; verify `import uldaq` and
   the *"Real uldaq detected"* log.
2. Plug board; `python -m pioner.runUI`; confirm the A1 status reads **REAL DAQ**.
3. Idle connect sanity: live stream ticks; Thtr shows `---` at idle (A3).
4. **P0-5 loopback** (when trigger wired): 1 kHz square AO ch1 -> AI ch1, leading
   edge within 1 sample with `HardwareTrigger=true`; compare to `false`.
5. Short fast / slow / iso runs vs reference data.

---

## Critical files

- `back/device_controller.py` -- A1/B2 backend-kind property.
- `front/mainWindow.py` -- A1 label set, A2 diagnostics, A3 idle Thtr.
- `front/mainWindowUi.py` -- A1 status QLabel.
- `shared/constants.py`, `shared/settings.py`, `settings/settings.json`,
  `src/pioner/settings/default_settings.json` -- B1 config plumbing (two JSONs).
- `back/experiment_manager.py` -- B3 sample-count logging.
- `shared/calibration.py` -- C2 docstring fix.
- `tests/test_calibration.py` (or new) -- C1 pinning test; new trigger round-trip
  test (B1) likely in `tests/test_ui_settings.py`-style settings test.
- `todo.md` -- C3 cross-link; note B1 closes the configurable-trigger gap.
- `docs/hardware-bringup.md` (new) -- E checklist.
- `hardware-plans.md` (this document, repo root).

## Reuse (do not re-implement)

- `mock_uldaq.DAQ_AVAILABLE` -- single real-vs-mock source.
- EXTTRIGGER path (`experiment_manager.py`, `daq_device.fire_software_trigger`)
  -- B1 only wires config to it.
- `Calibration.read` / `.ihtr0` / `.ihtr1` -- C1 reuses.
- `parse_daq_params` interface_type/connection_code pattern -- B1 mirrors it.

## Verification (mock / static -- live board deferred)

1. `python3 -c "import ast; ..."` on every edited `.py`.
2. `.venv/bin/pyright` -> stay **0 errors, 0 warnings**.
3. `PYTHONPATH=src .venv/bin/pytest -q` -> 94 pass + C1 pinning + B1 round-trip.
4. B1 unit test: a settings JSON with `HardwareTrigger:true` ->
   `daq_params.hardware_trigger is True`.
5. `QT_QPA_PLATFORM=offscreen` GUI smoke: connect (mock) -> status reads MOCK;
   fast/slow/iso run; A3 idle Thtr shows `---`.
6. `python -m pioner.runUI --mock` interactive sanity; restore
   `data/exp_data.h5` if a run clobbers it.
7. **Deferred to live board (HARD STOP):** E steps 2-5.

## Out of scope / explicit follow-ups

- **Tango repair** (P1-17 Approach B) -- deferred.
- **Live-chip accuracy items** (validation-only, cannot pre-fix on mock): P0-4
  iso AO seamlessness at 37.5 Hz, P1-9 lock-in edge transients, fast/slow
  live-stream-during-run (P1-17 Approach A, alignment >1000 K/s).
- **SI recalibration** of `ihtr1` (P2-21) -- pinning (C) is the interim guard.
