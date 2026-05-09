# CLAUDE.md — working agreement for this repo

PIONER is the back-end for the PIONER chip nanocalorimeter (DAQ, AC modulation,
software lock-in, three experiment modes: `fast`, `slow`, `iso`). Tests run
against a mock uldaq backend.

## Quick orientation

- Source: `src/pioner/{back,front,shared}`. Package name on PyPI is `ppioner`,
  import path is `pioner`.
- Tests: `PYTHONPATH=src .venv/bin/pytest -q` (33 passing on mock backend).
- Manual mock smoke: `python -m pioner.back.debug` runs all three modes.
- Editable install: `.venv/bin/pip install -e .` (already done; required so
  Pylance can resolve `pioner.*` imports without red squiggles).
- Pipeline reference: `spec.md`. Open backlog: `todo.md`. Mock pipeline check:
  `mock_verification.md`. Higher-level architecture: `design_notes.md`.

## Response style

- Default to concise, concrete answers. No filler, no recap of what was just
  said, no trailing summaries.
- Expand only on explicit request ("explain in detail", "walk me through",
  etc.).
- When changing a method, verify the change in two passes: first read the new
  code end-to-end, then re-read it against every call site to confirm callers
  still hold.
- For non-trivial code changes that affect rendering, run a static check
  (`python3 -c "import ast; ast.parse(open(p).read())"`) and `--help` smoke
  test BEFORE triggering a full render. Catches typos in seconds instead of
  minutes.
- Use `TodoWrite` only for multi-step tasks (>=3 sub-tasks). Skip for one-line
  edits and single-command runs.

### Anti-hallucination

- Verify before claiming. Cite `file.py:line` or grep output for any claim
  about code (function name, flag, signature, behaviour). Do NOT invent API
  calls, library functions, CLI flags, config keys, or URLs.
- Distinguish verified facts from inferences. If something is not directly
  checked, say so: "I think...", "probably...", "haven't verified". Avoid
  confident-sounding guesses.
- If a question needs information you don't have - the user's intent, an
  external spec, a runtime value - ASK rather than assume. One concrete
  clarifying question beats five wrong steps.
- When the user states a fact you'd have guessed differently (e.g. correcting
  a hardware spec), verify against what's already in the repo before accepting
  or pushing back. Don't auto-comply, don't auto-disagree.
- If a tool call output disagrees with your prior belief, trust the tool.
  Update the answer instead of explaining away the discrepancy.
- If you cannot do something the user asked for (missing data, wrong tool,
  environment limit) - say so directly. Do not produce a plausible-looking but
  fabricated result.
- Don't invent unit/scale assumptions. Calibration `ihtr1` is in `1/Ω` (so
  `ih = ihtr0 + ihtr1 * V_shunt` is in amperes). The default test calibration
  uses identity `ihtr1 = 1.0` and is dimensionally meaningless — never use it
  to back out physical numbers. State the unit convention you assumed.

## Conventions

- ASCII only — in code, comments, docstrings, identifiers, and string
  literals.
- C/C++ header extension: `.h` (not `.hpp`). Applies to all new headers and
  includes.
- Geometry work: prefer `mrmeshpy` (MeshLib) whenever it can do the job. If
  another library is a clearly better fit, use it but add a comment naming the
  library and the reason.
- Hardcoded values left intentionally untouched per project convention:
  column name `Uref` (not `Uheater`), heater channel literal `"ch1"`, and the
  `total_ms % 1000 == 0` software constraint on profile durations. Don't
  "clean these up" without an explicit ask.

## Physics & DAQ — load-bearing rules

These are the things that go wrong silently and produce numbers that *look*
right but aren't. Keep them in mind when touching `back/modes.py`,
`back/experiment_manager.py`, or anything in `shared/`.

- **Units in identifiers and comments.** Time is **ms** in user-facing arrays
  (program tables, GUI), **s** at the DAQ boundary. Voltages are **V** at the
  AO/AI boundary, **mV** after front-end gain (`df[4] *= 1000/gain_utpl`,
  `df[5] *= 1000`). Currents are **A** after `ihtr1` is applied. When you add
  a variable, name or comment its unit (`time_s`, `u_aux  # V`,
  `ih  # amperes`).
- **Don't mix °C and K.** Chip calibration polynomials and AD595 correction
  are in °C; never feed them Kelvin. Heater target temperature in user
  programs is °C.
- **Calibration dimensions.** `apply_calibration` in
  `src/pioner/back/modes.py` assumes `ih = ihtr0 + ihtr1 * V_shunt` yields
  amperes, so production `ihtr1 ≈ 1/Rshunt ≈ 5.88e-4` (Rshunt ≈ 1700 Ω).
  Identity `ihtr1 = 1.0` is the **test fallback only** — `Rhtr` derived from
  it has units of `Ω·V/A`, not Ω. See `todo.md` P0-3.
- **Heater R undefined at zero current.** When `|ih| < 1e-9 A` mark `Rhtr` as
  NaN. Never let `R = U/0` propagate; the legacy code produced ~−1070 °C and
  it took a long time to track down.
- **AC modulation + software lock-in.** Lock-in frequency must be strictly
  below Nyquist (`f_mod < ai_sample_rate / 2`). Integration window should
  cover an integer number of modulation periods to suppress `2f` leakage —
  `lockin_demodulate` does this; if you change the windowing, re-verify
  amplitude against the analytical value (mock check tolerates ~10 %, see
  `mock_verification.md`).
- **AO/AI start ordering.** AI must be armed before AO is started; the
  reverse skews the leading edge. See `todo.md` P0-5.
- **Buffer-length constraint.** Total program duration must be a whole number
  of seconds (`total_ms % 1000 == 0`). The AI buffer is sized to exactly one
  second; lifting this requires touching `_collect_finite_ai`.
- **Iso / CONTINUOUS scans tile `Uref`.** The AO buffer replays indefinitely;
  the AI frame is longer than one period. `apply_calibration` tiles the
  commanded voltage to match AI length so `Uref` reflects what was actually
  on the wire at every AI sample, not just the first second.
- **Safe-voltage clamp protects the chip.** `temperature_to_voltage` clamps
  to `[0, safe_voltage]`; `SlowMode`/`IsoMode` re-clip after adding the AC
  modulation. Don't bypass these — overshoot melts the heater.
- **AD595 cold-junction.** Channel 3, scaled 100 °C/V, with a polynomial
  correction below −12 °C (`hardware.correct_ad595`). Currently averaged over
  the whole scan, so for slow ramps >30 s expect up to ~0.5 °C drift error;
  see `todo.md`.
- **Mock vs. real hardware.** Tests run against `back/mock_uldaq.py`. Behaviour
  there is *plausible*, not bit-exact; physical-fidelity claims must be
  reproduced on real hardware before they're load-bearing.

## Token efficiency

- `Read`: always pass `offset` + `limit` for files >100 lines. Find the line
  first with `grep -n`, then read the slice. Do NOT re-read a file already in
  context.
- `Bash`: pipe long output through `tail -N`, `head -N`, or `grep -E "..."` at
  call time. Never `cat` a large file or pipe a full log. If you don't know
  the size, do `wc -l` first.
- `Monitor`: narrow regex on terminal markers only ("done|Error|Saved"), never
  `tail -f` raw streams.
- For long jobs use `run_in_background: true` + `Monitor` with strict filter;
  do not poll.
- Parallelise independent tool calls in one message (multiple `Read`/`Bash`
  together) instead of sequential turns.
- Do not reuse `Read` to "verify" an `Edit` - Edit fails loudly if the change
  did not apply.
- Skip redundant exploration (`ls`, `git status`) when prior output is still
  valid.
- Prefer `Edit` over `Write` for partial changes. `Write` re-sends the whole
  file; `Edit` sends only the diff.
- Don't recap completed steps unless asked. End the turn with the result, not
  a summary of how you got there.
- For trivial confirmations ("ok", "yes", "go ahead") - single-line ACK or
  just proceed silently. No restating context.
- Sub-agents (`Agent`) carry their own context overhead. Use only for genuine
  multi-step exploration that would pollute the main context, not for one
  grep.
- When asking the user a clarifying question, batch all related questions
  into ONE `AskUserQuestion` call, not sequential.
