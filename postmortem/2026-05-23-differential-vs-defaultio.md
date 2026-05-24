# DIFFERENTIAL vs DEFAULTIO confusion

**Date:** 2026-05-23
**Scope:** `src/pioner/back/ai_device.py`, README.md, design_notes.md,
todo.md, known-issues.md, docs/ir-merge-questions.md
**Impact:** dead-code fallback that would have failed loudly on real
hardware if it had ever fired; multiple AI-introduced wrong facts in
documentation; one diagnostic lead (operator's "switched single-ended
to default") wasted because the wrong axis was investigated.

---

## Symptom and context

While investigating an old `ULError.OVERRUN: FIFO overrun` crash on
fast-heat acquisition (operator's machine, pre-IR-branch code path; see
[../known-issues.md](../known-issues.md) section 1 for the full
incident), the operator's recollection of the fix included this phrase:

> "когда поменял режим с single-ended на дефолтный и после этого
> пропало."

(Translation: "when I switched the mode from single-ended to default,
the [crashes] went away.")

That quote was ambiguous. In uldaq there are two unrelated "modes"
that could fit:

- **`AiInputMode`** -- how the ADC samples voltage at the AI pin:
  - `DIFFERENTIAL = 1` (read voltage as difference between two pins)
  - `SINGLE_ENDED = 2` (read voltage relative to AGND)
- **`ScanOption`** -- how the scan itself behaves:
  - `DEFAULTIO = 0` (single-shot finite scan)
  - `CONTINUOUS = ...` (loop forever, wrap the buffer)
  - plus bit-flag modifiers like `BLOCKIO`, `EXTTRIGGER`, etc.

The word "default" in the operator's quote matched both options
syntactically: `DEFAULTIO` is literally named "default I/O", and
`DIFFERENTIAL` is sometimes informally called the "default" professional
input mode on multi-mode boards.

The known-issues.md entry initially documented both possibilities as
open hypotheses, leaving the input-mode angle as a leading "(Possibly)
switch input mode to DIFFERENTIAL" workaround in the workarounds list.

---

## What we assumed (wrongly)

1. **The codebase assumed `AiInputMode.DIFFERENTIAL` was a viable fallback.**
   `src/pioner/back/ai_device.py:73-74` had silent fallback code:

   ```python
   if info.get_num_chans_by_mode(ul.AiInputMode.SINGLE_ENDED) <= 0:
       self._params.input_mode = ul.AiInputMode.DIFFERENTIAL
   ```

   That is: "if the board doesn't expose SINGLE_ENDED channels, silently
   switch to DIFFERENTIAL." The fallback assumed boards generally have
   both modes available.

2. **`todo.md` P1-10 and P2-11 captured the fallback as a real concern.**
   P1-10 described the fallback as a known refactor target (the issue
   being that it mutates the shared `AiParams` object); P2-11 listed a
   test fixture "INPUT_MODE fallback to DIFFERENTIAL" as desirable test
   coverage. Both treated DIFFERENTIAL as a real (if rare) code path.

3. **README.md, design_notes.md, and an `experiment_manager.py` comment
   referenced USB-1808 / USB-2408 / `SyncIo`** as the "production boards"
   in scope, with claims about shared internal pacer clocks. None of
   those models is what is actually in the lab.

4. **`docs/ir-merge-questions.md` H1** asked the IR-branch developer
   whether the "switch to default" fix was `ScanOption.DEFAULTIO` or
   `AiInputMode.DIFFERENTIAL`, treating both as live possibilities.

5. **`known-issues.md` workarounds** included
   "(Possibly) switch input mode to `DIFFERENTIAL`" as a real-sounding
   suggestion, with a TODO to confirm.

---

## What was actually true

The operator informed us the lab board is **MCC USB-2637**, and added
the constraint: "у нас 2637, других нет" (USB-2637 only, nothing else).

Reading [`specs/USB-2637.pdf`](../specs/USB-2637.pdf) chapter 5
"Specifications", Analog Input table (table 1):

> Number of channels: **64 single-ended**

There is no mention of `DIFFERENTIAL` anywhere in the user's guide.
Cross-checked against the USB-2600 series datasheet
[`specs/USB-2600-Series-data.pdf`](../specs/USB-2600-Series-data.pdf)
page 1 selection chart: the USB-2623, USB-2627, USB-2633, and USB-2637
all list "16 SE" or "64 SE" -- no differential variant in the family.

**USB-2637 has no differential mode.** It is single-ended only.

The implication for the operator's quote: "default" cannot have meant
`AiInputMode.DIFFERENTIAL`, because that mode does not exist on the
board. It almost certainly meant `ScanOption.DEFAULTIO` -- the scan
option that the IR-branch fix actually uses (see
[../pioner-IR-branch/pioner_app/hardware/ai_device.py:251](../pioner-IR-branch/pioner_app/hardware/ai_device.py)).

The OVERRUN fix was on the scan-option axis (CONTINUOUS -> DEFAULTIO).
The input-mode axis was a red herring caused by ambiguous wording.

---

## How the truth was established

Step by step:

1. **Operator correction (2026-05-22):** stated the board is USB-2637,
   not the USB-1808 / USB-2408 that prior Claude Code sessions had
   inserted into README and design_notes.
2. **`git blame` on the legacy USB references:** showed all three
   (README.md:15, design_notes.md:190+, experiment_manager.py:184) came
   from earlier AI sessions (commits `ebeaa937`, `a441858d`,
   `a1639ad4`), not from a real hardware decision. No physical source
   document was ever cited.
3. **Read `specs/USB-2637.pdf` chapter 5:** confirmed "64 single-ended"
   in the AI specs, no DIFFERENTIAL row anywhere.
4. **Read `uldaq.ul_enums.AiInputMode`** (locally at
   `.venv/lib/python3.11/site-packages/uldaq/ul_enums.py:227-235`):
   confirmed enum values DIFFERENTIAL=1, SINGLE_ENDED=2, PSEUDO_DIFFERENTIAL=3
   and that `config.json: "InputMode": 2` is indeed SINGLE_ENDED.
5. **Cross-checked the IR-branch fix:** `ScanOption.DEFAULTIO`, full-scan
   buffer, no per-chunk read during the scan. Functions through DMA
   without active host involvement -- consistent with eliminating
   FIFO-overrun pressure.

Conclusion: the operator's memory conflated two independent fixes
(or remembered one fix wrong). The scan-option change is the one that
matters; the input-mode angle is impossible on this board.

---

## What was changed

### Code

- [src/pioner/back/ai_device.py:73-83](../src/pioner/back/ai_device.py#L73)
  -- silent fallback to `AiInputMode.DIFFERENTIAL` removed; replaced by
  a `RuntimeError` that explains the USB-2637 single-ended-only
  assumption. If the AI device ever reports zero SINGLE_ENDED channels,
  PIONER now fails loudly at connect time rather than pushing an
  unsupported mode and crashing later.

### Documentation

- [README.md:13-19](../README.md#L13)
  -- "USB-1808 / USB-2408" replaced with USB-2637, with the
  single-ended-only and independent-pacer-clocks facts called out.
- [design_notes.md:190-194](../design_notes.md#L190)
  -- "Boards in scope" rewritten for USB-2637 only, with TTLTRG spec
  and trigger latency from the datasheet.
- [design_notes.md:217-224](../design_notes.md#L217)
  -- "Pacer-clock sharing" option (legacy USB-1808 `SyncIo` mode)
  marked as not available on USB-2637; pointer to options 1-2
  (trigger-based sync) as the path forward.
- [src/pioner/back/experiment_manager.py:178-191](../src/pioner/back/experiment_manager.py#L178)
  -- comment about USB-1808 SyncIo replaced with a description of how
  USB-2637 can share a pacer clock externally via an XDPCR->XAPCR
  jumper.

### Tracking

- [todo.md P1-10](../todo.md): marked **resolved** -- the original
  refactor target (don't mutate shared `AiParams`) is moot once the
  mutation is gone.
- [todo.md P2-11](../todo.md): test fixture "INPUT_MODE fallback to
  DIFFERENTIAL" replaced with "hard RuntimeError when zero SE channels".
- [known-issues.md](../known-issues.md): workaround "(Possibly) switch
  input mode to DIFFERENTIAL" deleted; TODO entry for the
  "single-ended -> default" hypothesis rewritten with the resolution
  (it almost certainly meant DEFAULTIO, not DIFFERENTIAL); separate TODO
  for FIFO depth closed by citing the 4 kS / 2 kS values from the
  datasheet.
- [docs/ir-merge-questions.md H1](../docs/ir-merge-questions.md#h1):
  question simplified -- no longer asks "DEFAULTIO or DIFFERENTIAL?";
  now asks only "please confirm the fix was DEFAULTIO."

### New documentation

- [docs/usb-2637-vs-2627.md](../docs/usb-2637-vs-2627.md): direct
  spec-sheet comparison of USB-2637 against USB-2627 (which also lives
  in `specs/` for reference). Three things differ (16 vs 64 SE channels,
  16 vs 64-element channel queue, 3 vs 4 ribbon-cable headers).
  Everything else identical, including the 4 kS / 2 kS FIFO.

---

## Root cause

Two compounding causes:

1. **AI sessions producing plausible-sounding hardware facts without
   evidence.** Three different prior Claude Code sessions wrote
   USB-1808 and USB-2408 into the documentation as "the reference
   board", with associated claims about its trigger and `SyncIo` mode.
   None of those facts was anchored to a datasheet, a `git log`
   reference, or an operator statement. They were AI-generated examples
   that became "fact" by being committed. The same goes for the
   `DIFFERENTIAL` fallback in `ai_device.py`: a defensive-looking
   pattern that was probably copied from a more general MCC code
   example, not measured against actual hardware.

2. **Ambiguous operator quotes that an LLM should have asked to
   disambiguate.** "Switched from single-ended to default" matches both
   `AiInputMode` (operator-meaningful term) and `ScanOption` (uldaq
   term). The right response on first reading was a single clarifying
   question ("do you mean the scan option or the channel input mode?")
   rather than treating both options as parallel hypotheses. The
   hypotheses propagated into TODO lists and merge-question docs and
   wasted attention.

---

## Lessons

1. **Never claim a hardware fact without citing a primary source.** If
   a model name, FIFO size, channel count, or pacer-clock topology
   appears in documentation, it must trace to a datasheet line, an
   operator statement on record, or a git log entry. AI-introduced
   guesses go in `known-issues.md` TODO with an explicit "unverified"
   tag, not into prose written as fact. This is now codified in
   [`CLAUDE.md`](../CLAUDE.md) under "Flag uncertainty explicitly"
   (core rule 4) -- the actionable form for hardware claims is "if you
   would not bet on it from the datasheet, mark it `[?]`".

2. **Disambiguate ambiguous operator phrasing immediately.** When the
   user describes a fix in words that could mean two different uldaq
   constants, ask once. The cost of a one-line clarifying question is
   negligible compared to the cost of propagating both branches through
   docs, code comments, and merge plans.

3. **Postmortem the AI-introduced wrong facts when you find them.** It
   is tempting to silently fix them and move on. Writing it down here
   means: the next time someone reads `git blame` and sees
   "Opus 4.7 improvements" on a paragraph about USB-1808, they have
   context to know that paragraph was already corrected once. Otherwise
   the wrong claim cycles back through training data and re-emerges.

4. **Spec-cite numerical claims, especially in long-lived comments.**
   The comment "USB-1808 supports this and it needs no external wiring"
   in `experiment_manager.py:184` looked authoritative because it was
   in a code comment, with confident wording. It was wrong for the
   actual hardware. Format for code comments now: when a hardware
   capability is referenced, append the spec file path (e.g.,
   `# see specs/USB-2637.pdf chapter 5, External Clock I/O`) so the
   next reader can verify in one click.

---

## Open follow-ups

- [ ] Confirm with the operator that the original OVERRUN fix was
  `ScanOption.DEFAULTIO` (not an input mode change), to formally close
  [docs/ir-merge-questions.md H1](../docs/ir-merge-questions.md#h1).
  Low priority; current resolution is consistent.
- [ ] Reproduce the FIFO-overrun crash on **mainline** `finite_scan`
  (which still uses `ScanOption.CONTINUOUS` with a 1 s buffer) at
  20 kHz x 6 ch x 3 s, to confirm whether mainline needs the same
  DEFAULTIO-style restructuring as the IR branch already did. This is
  the larger open item from
  [known-issues.md](../known-issues.md) section 1 and is not
  postmortem-blocked.
- [ ] Audit `src/pioner/back/mock_uldaq.py` and `tests/` to ensure the
  new hard-RuntimeError path is covered (P2-11 in
  [todo.md](../todo.md)).
