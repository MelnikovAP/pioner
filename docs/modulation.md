# Modulation, lock-in detection, and demodulation

Reference document for the AC-modulation pipeline used by PIONER's `slow`,
`iso`, and modulation-only experiments. Theory first, then how each piece
maps to the code in the mainline `src/pioner` tree and in
`pioner-IR-branch/`.

ASCII math conventions used below:
`pi`, `omega = 2*pi*f`, `phi` for phase lag, `sin`/`cos` for trig,
`*` for multiplication, `<...>` for time-average / low-pass.

---

## Theory

### 1. Why modulation at all

Directly measuring a DC signal (e.g. a slow temperature drift on a
nanocalorimeter chip) is dominated by:

- `1/f` amplifier noise (grows toward DC as `1/f`),
- thermocouple offsets and drift,
- 50/60 Hz mains pickup,
- slow zero drift of the ADC.

The standard workaround is to **shift the useful signal out of DC into a
narrow band around a carrier frequency `f`** (e.g. 37.5 Hz), where the noise
floor is much lower. To do that we modulate the heater drive:

```
U(t) = U_DC(t) + A * sin(2*pi*f*t)
```

The chip then heats sinusoidally and its temperature oscillates at the same
`f`, lagging by some phase `phi` due to thermal inertia:

```
T(t) = T_DC(t) + dT * sin(2*pi*f*t - phi)
```

The physically meaningful observables are the AC amplitude `dT` and phase
`phi`. From them we extract heat capacity:

```
C_p(T) ~ P_AC / (omega * dT) * cos(phi)
```

The signal-processing problem is now: given a noisy ADC trace, recover `dT`
and `phi` at the known carrier `f`.

### 2. Demodulation in one sentence

Demodulation = "drop the envelope back to DC by multiplying by the carrier
and low-passing the result."

We use the trig identity:

```
sin(a) * sin(b) = (1/2) * [cos(a-b) - cos(a+b)]
```

Multiply the signal `s(t) = A * sin(omega*t - phi)` by the reference
`sin(omega*t)`:

```
s(t) * sin(omega*t) = (A/2) * cos(phi) - (A/2) * cos(2*omega*t - phi)
                      \_________________/   \_______________________/
                          DC component         component at 2f
```

After a low-pass filter that kills the `2f` term, what is left is the
constant `(A/2) * cos(phi)`. The useful signal has been moved from `f`
back to DC. This is the heart of demodulation.

### 3. Sine alone is not enough -- the I/Q pair

The single-sine projection above produces `(A/2) * cos(phi)`. If `phi`
happens to be near `pi/2`, that scalar is zero and the amplitude is lost.

Fix: multiply the input by **both** sine and cosine references in
parallel:

```
s * sin(omega*t)  --LP-->  I = (A/2) * cos(phi)     "in-phase"
s * cos(omega*t)  --LP-->  Q = (A/2) * sin(phi)     "quadrature"
```

`(I, Q)` is a pair of orthogonal projections. Amplitude and phase fall out
of the Pythagorean / arctan combination:

```
A    = 2 * sqrt(I^2 + Q^2)
phi  = arctan2(Q, I)              (sign depends on convention; see Sec. 9)
```

The factor of 2 cancels the `(A/2)` from the trig identity. This (I, Q)
representation is the standard "I/Q demodulation".

### 4. Lock-in amplifier

Lock-in (synchronous detector) = the whole chain above in hardware or in
code. The name is literal: the detector is "locked in" on the reference
phase, and only signal components coherent with the reference at frequency
`f` survive the low-pass filter.

```
   AI raw signal s(t)
        |
        +-- * sin(2*pi*f*t)   --> LP-filter --> I
        |
        +-- * cos(2*pi*f*t)   --> LP-filter --> Q
                                                |
                              A = 2*sqrt(I^2+Q^2),   phi = -arctan2(Q, I)
```

The key property: the effective measurement bandwidth equals the **LP
filter bandwidth**, not the input bandwidth. If the LP cuts at 0.1 Hz, the
effective bandwidth around the carrier `f` is also 0.1 Hz; everything else
is rejected. That is how lock-in detectors recover signals with raw SNR
far below unity.

### 5. Low-pass filter (LP)

LP = low-pass filter. Passes slow changes, rejects fast ones.

After the sin/cos multiplication, each branch contains:

```
I(t) = (A/2) * cos(phi)             <-- useful, DC or slowly varying
     + (A/2) * cos(2*omega*t - phi) <-- garbage at 2f
     + noise at other frequencies
```

The LP keeps the first term and rejects the rest. Narrower cutoff means:

- better noise rejection,
- but longer settling time -- the lock-in becomes sluggish to changes
  in the modulation amplitude `dT(t)` itself.

The eternal lock-in trade-off: **bandwidth vs response time**.

LP variants that appear in this codebase:

- **Moving average** (rectangular window of N samples). Simple; the AC
  transfer function is a `sinc`, which does not roll off sharply, but if
  the window covers an integer number of carrier periods the `2f`
  component is killed analytically. We use it as a fallback in the
  scipy-less code path (`_moving_average_demod`).
- **Butterworth** -- smooth frequency response with no ripples, applied
  via `sosfiltfilt` (forward + reverse pass for zero phase delay). This
  is what bench-top lock-ins (SR830 et al.) do. Mainline default in
  `shared.modulation.lockin_demodulate`.
- **Hanning window** in the FFT path -- not an LP in the strict sense,
  but a window that reduces spectral leakage. Mainline `fft_demodulate`
  does not use Hanning because it slices an integer-cycle window
  (cleanest line shape).

### 6. FFT demodulation

Instead of multiplying in the time domain, compute the FFT of the input
and read amplitude / phase directly at the harmonic bin:

```
S[k] = sum_{n=0..N-1} s[n] * exp(-2*pi*j*k*n/N)        (numpy rfft)
        ^
        pick k_f = round(f * N / fs)

A    = 2 * |S[k_f]| / N
phi  = -pi/2 - arg(S[k_f])      (sin-reference convention -- see Sec. 9)
```

This is mathematically equivalent to a lock-in if:

- the window contains an **integer number of carrier periods** (so the
  bin falls exactly on `f`, no leakage),
- the signal is stationary (amplitude and phase do not drift across
  the window).

FFT advantages:

- higher harmonics (`2f`, `3f`) come for free in a single transform;
  in nanocalorimetry the `2f` component carries real physics
  (nonlinearity of C_p) and `3f` is a sanity check on heater linearity,
- one scalar `(A, phi)` for the whole window -- no bandwidth/response
  trade-off to tune.

Disadvantage: if the signal is non-stationary (the slow-mode case,
where `T_DC(t)` ramps across the window), the FFT averages over the
window and the per-sample dependence `dT(T_DC)` is lost. There you want
a time-domain lock-in that returns `(A(t), phi(t))` traces.

This is why mainline uses both:

- `SlowMode` -> `lockin_demodulate` (per-sample trace),
- `IsoMode` -> `lockin_demodulate` for diagnostics + `fft_demodulate`
  for the final scalar estimate at 1f / 2f / 3f.

### 7. Integer-cycle windows and AO buffer integrity

For a window of `N` samples at sampling rate `fs`, the number of carrier
periods in the window is:

```
cycles = N * f / fs
```

If `cycles` is an integer (say 75 cycles in the window), the FFT bin at
`f` is "clean": all the carrier energy concentrates into a single bin,
there is no leakage, and -- in `CONTINUOUS`-replay AO buffers -- the
transition from the last sample back to sample 0 is seamless (phase jump
= 0).

If `cycles` is fractional (say 75.3), then:

- FFT energy spreads into neighbouring bins -> recovered amplitude is
  biased low,
- in `CONTINUOUS` AO replay each wrap injects a phase jump of
  `2*pi * 0.3 = 1.88 rad`, contaminating both the drive itself and the
  recovered `C_p`.

`shared.modulation.check_ao_period_integrity` runs this check on the AO
buffer that IsoMode is about to play CONTINUOUS and logs a warning when
`cycles_drift != 0`.

The IR branch does not perform this check (flagged in
[README-IR.md](../README-IR.md) section 8).

### 8. `x2` mode / second-harmonic demodulation

There is a classic AC-calorimetry fact. If the heater is driven with a
**current** `I(t) = I_DC + I_AC * sin(omega*t)`, the dissipated power is:

```
P(t) = I(t)^2 * R
     = R * (I_DC + I_AC * sin(omega*t))^2
     = R * [I_DC^2 + 2*I_DC*I_AC*sin(omega*t) + I_AC^2 * sin(omega*t)^2]
     = R * [I_DC^2 + I_AC^2/2          <-- DC
            + 2*I_DC*I_AC * sin(omega*t)  <-- at f
            - (I_AC^2/2) * cos(2*omega*t) <-- at 2f
           ]
```

So the dissipated power has components at DC, `f`, **and `2f`**. The chip
temperature follows. Demodulating at `2f` gives you the `I_AC^2 * R / 2`
term -- the Sullivan-Seidel observable, used in pure-AC calorimetry
without DC heating.

In the IR branch, `x2_mode=True` is implemented by squaring the reference
signal (because `sin(omega*t)^2 = (1 - cos(2*omega*t))/2`, which contains
a reference at `2*omega`) and then running the same cross-correlation
fit. In mainline, the `2f` component drops out automatically from
`fft_demodulate(..., harmonics=(1, 2, 3))`.

### 9. Phase: physical meaning and convention

Phase `phi` is the time lag between the reference (the AO drive) and the
AI response (the chip temperature). Physically it encodes **thermal
inertia**:

- fast response (small thermal mass / strong coupling) -> `phi -> 0`,
- slow response -> `phi -> pi/2`,
- at very high modulation `f`, where the chip cannot follow,
  `phi -> pi/2` and `dT` falls off as `1/omega`.

Phase carries information about thermal resistance and thermal mass. It
appears in the `C_p` formula explicitly via the `cos(phi)` factor; you
cannot extract `C_p` without it.

Convention used throughout `src/pioner`:

```
signal = A * sin(omega*t - phi)         minus sign: positive phi = "trails reference"
```

so

```
phi = -arctan2(Q, I)                    minus to match the convention above
```

Wrapped to `(-pi, pi]`. This matches what SR830-class bench-top lock-ins
report.

---

## Implementation

Two parallel code paths exist: the mainline `src/pioner` and the
historical `pioner-IR-branch/`. They do similar things with different
APIs and different correctness guarantees.

### Mainline (`src/pioner`)

All modulation primitives live in
[src/pioner/shared/modulation.py](../src/pioner/shared/modulation.py).
The file is structured strictly by role:

| Function / class                      | Role                                                                                                    |
|---------------------------------------|---------------------------------------------------------------------------------------------------------|
| `ModulationParams` (dataclass)        | Frozen `(frequency, amplitude, offset)` triple read from settings.                                      |
| `apply_modulation`                    | Build the AO drive: `base_voltage + offset + amplitude * sin(2*pi*f*t)`. Adds AC to a DC profile.       |
| `lockin_demodulate`                   | Full time-domain lock-in: sin/cos demod, Butterworth `sosfiltfilt` LP (zero phase delay), with a moving-average fallback when scipy is unavailable. Returns per-sample `(amplitude, phase)` traces. |
| `fft_demodulate` + `FFTDemodResult`   | FFT-based demodulator with integer-cycle window selection (`_integer_cycle_length`) and multi-harmonic extraction (defaults `(1, 2, 3)`). Returns scalar `(amplitude, phase)` per harmonic plus a leakage fraction diagnostic. |
| `check_ao_period_integrity` + `AOPeriodReport` | Diagnostic on an AO buffer about to be played `CONTINUOUS`: reports cycles count, drift from integer, phase jump per wrap, leakage. Used by IsoMode to warn the user before a biased run. |

Per-mode wiring (in [src/pioner/back/modes.py](../src/pioner/back/modes.py)):

- **FastHeat**: no modulation, no demodulator. Just AO + AI finite scan.
- **SlowMode**:
  - `_build_profiles` adds AC to the heater channel via `apply_modulation`,
    clamps to `[0, safe_voltage]`.
  - `run` calls `lockin_demodulate` on `temp-hr` because the DC base ramps
    across the scan and the natural observable is the per-sample
    `amp(t)`, `phase(t)` trace. FFT would collapse the ramp into a single
    biased scalar.
- **IsoMode**:
  - `_build_profiles` tiles one second of modulated drive (since the AO
    is replayed `CONTINUOUS`), runs `check_ao_period_integrity` and logs
    a warning if the buffer is not seamless.
  - `run` collects samples into a ring buffer for the requested duration,
    then runs:
    - `lockin_demodulate` for the per-sample diagnostic trace,
    - `fft_demodulate` with `harmonics=(1, 2, 3)` for the scalar physical
      observable, including the 2f and 3f harmonics.
  - Disagreement between the two estimators flags either a thermal
    transient, a non-stationary signal, or a defective AO modulation
    buffer (see `_ao_period_report`).

`lockin_demodulate`'s LP defaults to `frequency / 5` (a common rule of
thumb that kills `2f` while keeping settling time short). The Butterworth
is 4th order; `sosfiltfilt` is used for zero phase-lag, matching what a
hardware lock-in produces.

Phase wrap convention: `(-pi, pi]`, lag-positive (`signal = A*sin(omega*t -
phi)`).

### IR branch (`pioner-IR-branch/`)

Demodulation primitives live in
[pioner_app/core/basemath.py](../pioner-IR-branch/pioner_app/core/basemath.py).
Three competing implementations coexist:

| Function                              | Algorithm                                                                                                   | Used by                                                |
|---------------------------------------|-------------------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| `lockin(Usig, fs, f)`                 | Plain sin/cos multiply + `np.mean` (= LP with window = whole signal). No proper LP filter.                  | Not called from production paths.                      |
| `fft_lockin(signal, fs, f)`           | Hanning window + `rfft` + nearest-bin amplitude/phase + coherent-gain correction. Single harmonic only.     | "FFT" choice in `DataProcessor.analyze_slow_heating_chunk`. |
| `calcaf_lockin(bufref, bufsig, fclk, fgen, ...)` | Port of the legacy C++ nanocalorimeter routine: builds a 1000-sample cross-correlation against the AO reference, runs an iterative LM-style fit (50 iterations) for amplitude / phase / offset, supports `modulation_amp` scaling, `x2_mode` (square the reference -> demodulate at 2f), and a manual `addphase` knob. | "Lock-in" choice (default) in the slow-heat panel and in the live `Values` sidebar of `mainWindow`. |

`calcaf_lockin` is the load-bearing demodulator in this branch. The
double `O(period * xperiod)` loops at
[basemath.py:93-116](../pioner-IR-branch/pioner_app/core/basemath.py#L93-L116)
and the iterative fit at
[basemath.py:137-169](../pioner-IR-branch/pioner_app/core/basemath.py#L137-L169)
are pure Python -- acceptable for the ~1 point/sec cadence of slow-mode
but unsuitable for per-sample demodulation.

What is **missing** vs mainline (none of these have an equivalent in
`basemath.py` or anywhere else in the IR branch):

- Proper LP filter (Butterworth / `sosfiltfilt`).
- Multi-harmonic FFT (2f, 3f) -- only the implicit `x2_mode` via
  reference squaring.
- Integer-cycle window selection in the FFT path. `fft_lockin` just
  takes the whole signal, so leakage is non-trivial when `N * f / fs`
  is not integer.
- Spectral leakage diagnostic.
- AO buffer integrity check. CONTINUOUS modulation buffers in
  `start_modulation` and `start_ao_continuous_mod` are not validated;
  a user-picked frequency that does not divide the buffer evenly will
  silently produce biased results.

Per-mode wiring in the IR branch:

- **Modulation only** ([daq_controller.py:189](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L189)):
  builds one period of `current_mA = offset + amp*sin(...)`, converts to
  volts via `(I/1000 - ihtr0) / ihtr1`, pushes to AO `CONTINUOUS`. No
  demod on this panel itself; analysis happens in the live Values
  sidebar at 250 ms cadence via `analyze_slow_heating_chunk`.
- **Slow heat** ([daq_controller.py:442](../pioner-IR-branch/pioner_app/hardware/daq_controller.py#L442)):
  AO worker thread builds DC ramp + AC (with optional F/A/P parameter
  ramps via `AOStreamSHGenerator`), finite scan. AI runs CONTINUOUS in
  parallel. UI polls the ring buffer at 100 ms cadence, slices chunks of
  integer modulation periods, picks demodulator from a combo
  ("Lock-in" -> `calcaf_lockin`, "FFT" -> `fft_lockin`), plots
  amplitude / phase / Ttpl / Thtr trends. With a calibration loaded,
  the demodulated channel is `temp_hr_trace` (so amplitude is `dT` in
  Celsius); without calibration it falls back to `Umod_mV`.
- **Fast heat**: no demodulation -- finite paced AO+AI scan only.
- **Iso**: not implemented as a first-class mode (see
  [README-IR.md](../README-IR.md) section 4.4).

Phase wrap convention in `calcaf_lockin`: `(-180, 180]` degrees, with a
manual `addphase` offset subtracted at the end. UI exposes a "zero phase"
button in the Values sidebar that stores the current `phase` as
`_phase_offset` and subtracts it on display
([mainWindow.py:479](../pioner-IR-branch/pioner_app/ui/mainWindow.py#L479)).

Mainline -> IR mapping for migration purposes:

| Mainline                                   | IR analogue                                  | Notes                                                                                 |
|--------------------------------------------|----------------------------------------------|---------------------------------------------------------------------------------------|
| `apply_modulation`                         | `AOGenerator.sine` + ad-hoc tile in `start_ao_continuous_mod` | IR has no single function; AO drive construction is scattered.                        |
| `lockin_demodulate` (per-sample trace)     | `calcaf_lockin` (scalar per chunk)           | Different output shape: IR returns one `(A, phi)` per analysis chunk, mainline returns per-sample arrays. |
| `fft_demodulate` (integer-cycle, multi-harmonic) | `fft_lockin` (Hanning, nearest bin, 1f only) | IR `fft_lockin` is biased on non-integer-cycle inputs.                                |
| `check_ao_period_integrity`                | none                                         | Add this before reusing IR's CONTINUOUS modulation paths.                             |

---

## Quick conceptual reference

- **Demodulation** = move a signal from the carrier `f` back to DC by
  multiplying with the carrier and low-passing the result.
- **Lock-in** = synchronous detector implementing demodulation, locked
  to a known reference; effective measurement bandwidth = the LP
  bandwidth.
- **LP (low-pass)** = filter that keeps slow / DC content and rejects
  high frequencies; in lock-ins it kills the `2f` mixing product left
  over from the multiplication.
- **I / Q** = orthogonal sin/cos projections that together encode both
  amplitude and phase, independent of which phase the input happens to
  have.
- **FFT demodulation** = the same operation done in the frequency domain
  by reading the amplitude / phase of the harmonic bin directly.
- **Integer-cycle window** = window length such that
  `N * f / fs` is an integer; required for FFT to be leakage-free and
  for CONTINUOUS AO replay to wrap without phase jumps.
- **`x2` mode** = demodulate at `2f` instead of `f`; physically relevant
  because heater power dissipation contains a `2f` component
  automatically when the drive is `I_DC + I_AC * sin(omega*t)`.
- **Phase `phi`** = lag between drive and response, encoding thermal
  inertia; enters the `C_p` formula directly as `cos(phi)`.
