# Design notes — three open back-end questions

Working notes on three open questions discussed in chat on 2026-05-09. Saved
here so the work can be picked up in a separate session without losing
context.

Items covered:
1. P1-1 — `IsoMode` external abort handle.
2. P0-5 — AO/AI start skew on real hardware.
3. Channel-key literals (`"ch1"`, `"ch2"`, …) — should we kill them?

---

## 1. P1-1 — `IsoMode`: external abort handle

### Problem

`IsoMode.run(duration_seconds=N)` blocks for exactly `N` seconds via
`time.sleep(N)` and only then stops. There is no `stop()` method, no
`threading.Event`, no Tango command that can interrupt it. Killing the
process is the only way to abort a 30-minute run.

The desired behaviour is **"set V (with optional AC), stream AI, run until
the user explicitly stops"**. That requires an external interrupt handle.

This same primitive is also needed for **P1-5** ("Set V & hold" legacy
scenario): both items want a long-lived AO output that the user can stop
on demand. Fix them together.

### Where the change lands

Three layers, ordered by dependency:

#### a. Backend — `_IsoMode` in `src/pioner/back/modes.py:447-573`

Add a per-instance `threading.Event`. Replace `time.sleep` with `Event.wait`.
Expose `stop()`.

Sketch (pseudo-diff against current code):

```python
class IsoMode(BaseMode):
    def __init__(self, ..., ring_buffer_seconds: float = 10.0) -> None:
        ...
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Request a clean shutdown of the running iso scan."""
        self._stop_event.set()

    def run(self, duration_seconds: Optional[float] = None) -> pd.DataFrame:
        ...
        self._stop_event.clear()                       # re-arm
        em = ExperimentManager(self._daq, self._settings)
        try:
            if params.enabled:
                em.ao_modulated(self._voltage_profiles)
            else:
                for ch, profile in self._voltage_profiles.items():
                    em.ao_set(int(ch.replace("ch", "")), float(profile[0]))

            em.start_ring_buffer(self._ai_channels,
                                 max_seconds=self._ring_buffer_seconds)
            # Block until either the timeout elapses OR stop() is called.
            # ``timeout=None`` => wait forever; ``timeout=N`` => max N seconds.
            self._stop_event.wait(timeout=duration_seconds)
            em.stop_ring_buffer()
            samples = em.snapshot_ring_buffer()
        finally:
            em.stop()
        ...
```

Semantics:
- `duration_seconds` becomes a **maximum** timeout, not a hard duration.
- `duration_seconds=None` → "wait forever, until `stop()` is called". This
  cleanly satisfies the "run until user stops" requirement.
- `stop()` is idempotent and thread-safe (Event semantics).

#### b. Tango — `nanocontrol_tango.NanoControl`

Add a command that delegates to the active mode. Same primitive should be
exposed for slow mode (long ramps may also want abort, particularly during
a temperature program editor mistake).

```python
@command
def stop_run(self) -> None:
    """Abort the currently-running mode (iso or slow)."""
    if self._mode is not None:
        self._mode.stop()
```

The active mode is whatever was returned by the last `arm()` call. Storing
it as `self._mode` is already the pattern used today.

#### c. Front-end (out of scope here)

A button bound to `device.stop_run()`. The wire-up is trivial once b. exists.

### What this also unlocks (P1-5)

Once `_IsoMode` has a `stop()` and the legacy `iso_mode.IsoMode` keeps an
`ExperimentManager` on `self`, `run(do_ai=False)` can become:

```python
def run(self, do_ai: bool = True, duration_seconds=None):
    if not do_ai:
        # "Set V and hold". Do not start AI, do not stop AO. Caller
        # turns it off later via ai_stop().
        self._em = ExperimentManager(self._daq, self._settings)
        if self._modulation.enabled:
            self._em.ao_modulated(self._mode.voltage_profiles)
        else:
            for ch, profile in self._mode.voltage_profiles.items():
                self._em.ao_set(int(ch.replace("ch", "")),
                                float(profile[0]))
        return None
    return self._mode.run(duration_seconds=duration_seconds)

def ai_stop(self) -> None:
    if self._em is not None:
        self._em.stop()
        self._em = None
```

Same `Event`/`stop()` infrastructure → both P1-1 and P1-5 closed.

### Edge cases to test

- `run()` started, `stop()` called from another thread within 0.5 s → run
  returns within ~1 s, snapshot has ~0.5 s of samples.
- `run()` with `duration_seconds=None` → blocks until `stop()` called;
  no spurious wake-ups.
- `run()` then `run()` again on the same instance → `_stop_event.clear()`
  must happen before the second `wait`.
- `stop()` called *before* `run()` → first `run()` returns immediately. Is
  that the desired contract or a bug? Probably should clear at the top of
  `run()` (sketch above does that) so a stale `stop()` is harmless.
- KeyboardInterrupt while `wait(timeout=None)` is blocked → Python's
  threading.Event.wait is interruptible by signals on the main thread; on
  worker threads it is not. Verify behaviour matches the GUI's expectation
  (usually only the Tango thread receives signals, so worker not needing
  signal-safety is fine).

### Verification

```python
# In tests/test_modes_e2e.py:
def test_iso_mode_can_be_stopped_early(connected_daq, settings, calibration):
    iso = IsoMode(connected_daq, settings, calibration, {"ch1": {"volt": 0.5}})
    iso.arm()
    t0 = time.monotonic()
    result = {}
    def runner():
        result["df"] = iso.run(duration_seconds=10.0)
    th = threading.Thread(target=runner); th.start()
    time.sleep(0.5)
    iso.stop()
    th.join(timeout=2.0)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"stop() did not interrupt in time ({elapsed:.2f}s)"
    df = result["df"]
    assert 0.3 * settings.ai_params.sample_rate < len(df) < 1.0 * settings.ai_params.sample_rate
```

---

## 2. P0-5 — AO/AI start skew

### Problem

[experiment_manager.py:179-194](src/pioner/back/experiment_manager.py#L179-L194)
arms AI first (`ScanOption.CONTINUOUS`), then AO (`ScanOption.BLOCKIO`),
then immediately enters the polling loop. There is no shared start trigger
— the two scans start sequentially in user-space code, separated by ~100 µs
of Python overhead and one USB round-trip per `scan()` call.

For a 1000 K/s FastHeat scan, 100 µs → ≤ 1 °C skew on the very first
sample. Acceptable for the mock and most slow/iso runs; a problem only at
the very leading edge of fast scans.

### Two ways to fix

#### Option A — shared hardware trigger (production answer)

Both scans configured with `ScanOption.RETRIGGER` or `ScanOption.EXTTRIGGER`
gated on the same digital trigger line.

Boards in scope (`README.md` references USB-1808 and USB-2408):

- **USB-1808 / USB-1808X** — exposes a digital trigger input on `TRIG`
  pin. Supports both `EXTTRIGGER` (one-shot) and `RETRIGGER`.
- **USB-2408** — same idea; check that the trigger line is wired in your
  socket harness.

Sequence:

```python
# Pseudocode for ExperimentManager.finite_scan:
self._ai_params.options = ul.ScanOption.CONTINUOUS | ul.ScanOption.EXTTRIGGER
self._ao_params.options = ul.ScanOption.BLOCKIO    | ul.ScanOption.EXTTRIGGER
ai_handler.scan(...)   # arms, blocks waiting for trigger
ao_handler.scan(...)   # arms, blocks waiting for trigger
# Issue the trigger pulse:
daq.fire_digital_trigger()   # boards typically expose this via DigitalIo
# Both scans start on the same DAQ clock edge.
```

Trigger source options, easiest to most flexible:

1. **Self-trigger via a free DOut line** — set up a digital output on the
   same DAQ board, wire it to the `TRIG` input externally, fire from
   software. One extra physical jumper, no extra equipment.
2. **External pulse generator** — clean but requires an extra piece of lab
   gear and a cable to it.
3. **Pacer-clock sharing** — if the board supports a single internal pacer
   that drives both AO and AI (USB-1808 does — `SyncIo` mode), no trigger
   line needed; both scans take samples on the same clock edge by
   construction. This is the cleanest answer if the board supports it,
   needs zero physical changes.

Validation procedure (real hardware, no chip in the socket):

1. Drive a 1 kHz square wave on AO ch1 with a clean DC offset.
2. Loopback AO ch1 → AI ch1 with a wire.
3. Run a 100 ms scan, find the first rising edge in the AI trace.
4. Compute `samples_to_first_edge`. With a hardware trigger this should be
   `<= 1` sample, ideally 0. Without it, expect 2-20 samples (the current
   behaviour).

The number you measure becomes the regression baseline for the test that
asserts the trigger is active.

#### Option B — software offset workaround (interim)

If the trigger upgrade slips, measure the skew once and trim it:

1. With the loopback test above, find the consistent offset `N` (in
   samples).
2. In `apply_calibration`, drop the first `N` rows and shift `time`
   accordingly. Add a `pre_trigger_samples` field to `Calibration` so the
   value is per-host configurable.

Caveats:

- Skew can drift across hosts, USB hubs, kernel versions. Re-measure after
  any of those changes.
- This makes `apply_calibration` host-specific, which is unpleasant. Keep
  it as a safety net, not a permanent solution.

### Recommendation

Plan A first. Try **pacer-clock sharing** (option 3) before adding any
external wiring — if `uldaq` exposes the right knob for your board, it's
zero-hardware-change. Fall back to a self-trigger DOut jumper otherwise.
Plan B only if A is blocked and you need to ship.

### Where the change lands

- `src/pioner/back/experiment_manager.py:179-194` — add the trigger
  options. Today this is a single TODO comment and two `options =`
  assignments.
- `src/pioner/back/ao_device.py`, `src/pioner/back/ai_device.py` — both
  `scan()` methods pass `options` through to `a_*_scan` already; the
  trigger flag piggybacks on that. No structural change.
- New helper for firing the trigger pulse — likely `daq_device.py` since
  it owns the DAQ handle and the digital-IO subsystem belongs there.
- A new option / flag in `BackSettings.daq_params` to toggle trigger
  mode, so dev-on-mock keeps using software-sequenced start while real
  hardware turns on `EXTTRIGGER`.

### Mock implications

The mock does not need to change — it always starts AO/AI in zero
time-skew anyway. But the new trigger-config flag in `BackSettings` should
be a no-op on the mock (don't simulate a trigger; just start as today).
This means the mock is silent about trigger correctness — it has to be
verified on real hardware, full stop.

---

## 3. Killing `"ch1"` literals

### Problem

`"ch1"` (and friends) appear as raw strings in:

- User-supplied programs: `{"ch1": {"time": [...], "temp": [...]}}`.
- Default arguments: `modulation_channel: str = "ch1"` in
  `SlowMode.__init__`, `IsoMode.__init__`.
- `voltage_profiles` dict keys (round-tripped through HDF5 and Tango).
- `apply_calibration`'s `if "ch1" in voltage_profiles: ...`.
- ~15 call sites total.

The literal sprawl makes it impossible to grep for "the heater channel" —
you have to know the convention. It also makes channel reassignment a
risky search-and-replace.

### Three approaches with tradeoffs

#### Approach 1 — Named domain constants (minimal, recommended)

```python
# src/pioner/shared/channels.py
"""Named constants for the AO/AI channel layout.

Keep these as plain strings/ints — JSON, HDF5, and Tango wire formats use
those exact shapes. The point of this module is *naming*, not type-safety.
"""

HEATER_AO       = "ch1"   # AO ch1 — heater drive (DC + AC modulation)
GUARD_AO        = "ch2"   # AO ch2 — guard heater / trigger line
SHUNT_BIAS_AO   = "ch0"   # AO ch0 — shunt-path bias (~0.1 V)
SPARE_AO        = "ch3"

HEATER_CURRENT_AI = 0     # AI ch0 — heater current shunt
UMOD_AI           = 1     # AI ch1 — Umod (high-gain thermopile)
AD595_AI          = 3     # AI ch3 — AD595 cold-junction
UTPL_AI           = 4     # AI ch4 — Utpl (standard thermopile)
UHTR_AI           = 5     # AI ch5 — heater voltage feedback
```

Replace `"ch1"` with `HEATER_AO` everywhere except the user-program
input format (where `"ch1"` is a JSON wire key). Replace bare integers
like `if 4 in df.columns:` in `apply_calibration` with `if UTPL_AI in
df.columns:`.

**Pros**: minimal change (~15 call sites), no boundary converters, JSON
and HDF5 round-trip unchanged, semantic naming where it matters.

**Cons**: no compile-time guarantee that a channel literal hasn't been
typo'd. (mitigated by tests that exercise the full pipeline)

#### Approach 2 — `StrEnum` (Python 3.11+)

```python
from enum import StrEnum

class AoChannel(StrEnum):
    CH0 = "ch0"
    CH1 = "ch1"
    CH2 = "ch2"
    CH3 = "ch3"

class AiChannel(IntEnum):
    SHUNT  = 0
    UMOD   = 1
    AD595  = 3
    UTPL   = 4
    UHTR   = 5
```

`StrEnum` instances ARE strings: `AoChannel.CH1 == "ch1"` is `True`,
`json.dumps({AoChannel.CH1: ...})` works without a converter. Type
checkers can flag accidental misuse.

You can compose with Approach 1:

```python
HEATER_AO = AoChannel.CH1
```

**Pros**: type-safe, no boundary converters, semantic naming.

**Cons**: Python 3.11+ requirement (already targeted, see `pyproject.toml`
`requires-python = ">=3.10"` — would need to bump to 3.11). One extra
import per call site. Marginally heavier than Approach 1.

#### Approach 3 — Full `IntEnum` + helpers

```python
class Channel(IntEnum):
    CH0 = 0; CH1 = 1; ...

def chan_key(c: Channel) -> str: return f"ch{c.value}"
def parse_chan(s: str) -> Channel: return Channel(int(s.removeprefix("ch")))
```

Channels are integers internally; `"ch{N}"` strings appear only at JSON /
HDF5 / Tango boundaries via the helpers.

**Pros**: cleanest typing.

**Cons**: every dict-keyed-by-channel becomes a translation layer. JSON
(de)serialisation now needs the helpers in 3-4 places. `voltage_profiles`
keys become enums; HDF5 group names need explicit conversion. This is a
lot of glue for what is, fundamentally, a wire-format concern.

### Recommendation

**Approach 1 first**, optionally promote to **Approach 2 (`StrEnum`)** if
you want type-safety on top. Reasoning:

1. The pain point is *naming* — nobody reading the code knows why it's
   `ch1` vs `ch0`. A `HEATER_AO` constant fixes that immediately.
2. `"ch1"` is a wire format on the JSON / HDF5 / Tango layer. Adding an
   integer ↔ string translation everywhere (Approach 3) doesn't make the
   code clearer — the wire still uses strings — it just adds glue. The
   mental cost of two representations exceeds the value.
3. `StrEnum` is the sweet spot if you want compile-time discipline. It
   composes with Approach 1 — you don't have to choose now.

### Migration plan (Approach 1)

Single PR, ~half a day. Steps:

1. Create `src/pioner/shared/channels.py` with the constants above.
2. Sweep replace at call sites. Grep target list:
   - `src/pioner/back/modes.py` — defaults for `modulation_channel`,
     `if "ch1" in voltage_profiles`, `int(ch.replace("ch", ""))` → use a
     helper or constant.
   - `src/pioner/back/experiment_manager.py` — `ao_set(channel, …)` call
     sites.
   - `src/pioner/back/iso_mode.py` — legacy `_channel = int(…)`.
   - `src/pioner/back/fastheat.py` / `slow_mode.py` — HDF5 group keys.
   - `src/pioner/back/nanocontrol_tango.py` — JSON parsing on `arm`.
3. Leave the user-facing JSON program format (`{"ch1": {...}}`) as-is —
   that's the wire format, not internal code. Document `HEATER_AO ==
   "ch1"` once in `spec.md` and move on.
4. Existing tests in `tests/` use `"ch1"` literally in user programs —
   those stay because they are simulating user input (i.e. external API).
   That's correct usage; the literal *belongs* there.
5. New unit test: assert that `HEATER_AO == "ch1"` and `UMOD_AI == 1`.
   This is a one-liner that pins the wire format so someone changing the
   constants accidentally breaks the test, not a chip in the lab.

### Cancellation status

This was previously tracked as **P1-7** in `todo.md`, marked "explicitly
not doing — `ch1` remains a literal". User has changed their mind on
2026-05-09. When implementing, remove the corresponding line in
`todo.md`'s "Hardcoded values left intentionally untouched" note, and add
a P1 item describing this work.

---

## Summary — recommended order

If all three land this cycle:

1. **Channel constants (Approach 1)** — half-day, low-risk, makes the
   subsequent two PRs more readable. Do this first.
2. **P1-1 + P1-5 together** — same `Event`/`stop()` primitive solves both;
   one PR, plus the Tango command. ~1 day.
3. **P0-5** — needs real hardware to validate. Plan and prototype the
   pacer-clock-sharing approach in code, but flag it as
   blocked-on-hardware in `todo.md` until someone runs the loopback test.

None of the three blocks declaring MVP on the mock backend. P0-5 does
block declaring MVP on real hardware for FastHeat at >1000 K/s.
