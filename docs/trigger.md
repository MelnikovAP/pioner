# Trigger: analog vs digital, and what our board provides

## Physical difference

### Analog trigger

- The input accepts an arbitrary analog signal (e.g. +/-10 V).
- Inside the board sits a **comparator** with a programmable threshold
  (or the threshold is set by a dedicated trigger DAC). When `V_in`
  crosses the threshold, the comparator flips and signals the state
  machine.
- Lets you start on a physical event (e.g. rising edge of a photodiode
  signal, a thermocouple exceeding some temperature).
- Downsides: comparator delay + threshold drift + noise sensitivity
  (hysteresis required); threshold precision is limited by the
  trigger-DAC resolution.

### Digital (TTL) trigger

- The input expects a **logic level** (0 / 3.3 V or 0 / 5 V).
- Inside the board: ESD protection -> Schmitt-trigger input buffer ->
  synchronizer (chain of D flip-flops clocked by the internal clock) ->
  edge detector (rising/falling) -> state machine starts AO/AI.
- Latency is deterministic and low: on our board **1 us + 1 clock
  cycle** max (that figure is exactly the length of the synchronizer
  chain plus FPGA propagation).
- Minimum pulse width: 100 ns.
- Downside: the source must already emit a TTL-level signal. You
  cannot wire an arbitrary analog signal directly.

## Physical layout on our board

USB-2637 (see [usb-2637-vs-2627.md](usb-2637-vs-2627.md), section
"Trigger", lines 106-115):

- **Trigger source: TTLTRG** -- the only hardware trigger input, and
  it is **digital**.
- Software-configurable: edge-sensitive (rising/falling) or
  level-sensitive (high/low). Default: rising edge.
- Input electrical: 33 Ohm series resistor + 49.9 kOhm pull-down to
  GND. Logic levels: high >= 2.2 V, low <= 1.5 V, 5.5 V absolute max.
- Latency 1 us + 1 clock cycle max, minimum pulse width 100 ns.

**There is no analog trigger input on the USB-2637.** The board
documentation lists only TTLTRG as a trigger source (same file, lines
102 and 108). If you need to start on an analog event, you would have
to put an external comparator in front of TTLTRG.

## How this maps onto what already exists in the code

The `ScanOption.EXTTRIGGER` path is already wired up:

- [../src/pioner/back/experiment_manager.py](../src/pioner/back/experiment_manager.py),
  lines 194-221 -- both AO and AI are armed with `EXTTRIGGER`, then a
  single `fire_software_trigger()` call releases them on a shared t=0.
- [../src/pioner/back/daq_device.py](../src/pioner/back/daq_device.py),
  lines 139-152 -- `fire_software_trigger` goes through uldaq and
  generates an internal pulse on TTLTRG (or its state-machine
  equivalent). So **physically it is the same digital trigger**; the
  pulse is just produced by the board itself in response to a USB
  command, not driven from outside.

## Options for a "real" external digital trigger

1. Drive TTLTRG with a TTL pulse from an external source (Arduino,
   function generator, signal from another board) -- the shared t=0
   then synchronizes with that external instrument.
2. Loop one of the 24 DIO lines
   ([usb-2637-vs-2627.md](usb-2637-vs-2627.md), lines 129-137) back to
   TTLTRG -- you still control the trigger from software (via DIO),
   but the edge is a real wired pulse that can be probed with a
   scope. Latency / jitter is equivalent to `fire_software_trigger`,
   just observable on the wire.

## Triggering an external instrument *from* the nanocal

The reverse direction -- nanocal acts as the trigger source for another
device -- is supported too. Three options on USB-2637, ranked by timing
quality:

### 1. Analog output (AO / XDAC0..3) -- the natural fit for an analog trigger

See [usb-2637-vs-2627.md](usb-2637-vs-2627.md), lines 88-98.

- 4 channels, +/-10 V, 16-bit, **1 MS/s**, settling 2 us, slew rate
  20 V/us.
- Drive +/-3.5 mA -- enough for a scope or a high-Z instrument input,
  not enough for a relay or a motor.
- Timing is locked to the AO pacer clock. You can place the "trigger
  edge" at any specific sample in the programmed AO waveform, and it
  appears on the pin synchronously with the heater current /
  modulation, accurate to one AO clock tick.
- Per the design intent (same doc, line 193) **ch2 is already
  reserved as a trigger output**: ch0 modulation, ch1 heater drive,
  ch2 free for an external trigger.

### 2. Timer outputs (TMR0..TMR3) -- the right path for a hardware-precise TTL pulse

See [usb-2637-vs-2627.md](usb-2637-vs-2627.md), lines 148-154.

- 4 PWM / square-wave channels, **fully hardware-driven**, no USB in
  the path.
- Internal 64 MHz clock, minimum pulse width **10.42 ns**, 32-bit
  registers.
- This is the correct option for "nanocal -> external instrument"
  over TTL with deterministic latency.

### 3. DIO (24 TTL lines as output) -- only when timing does not matter

See [usb-2637-vs-2627.md](usb-2637-vs-2627.md), lines 129-137.

- Each line is programmable as output. Levels: high >= 4.4 V,
  low <= 0.1 V -- standard TTL.
- **Caveat:** the doc states
  `Transfer rate (system-paced, async): 33-4000 reads/writes per second`
  (line 134). DIO is driven by software over USB, so latency and
  jitter are tens to hundreds of microseconds and not predictable.
  Do not use DIO when "the edge must land at time t" matters.

### What is NOT available

The TTLTRG pin on the board is **input only** (lines 113-115:
pull-down resistor, input thresholds). There is no "trigger out" on
the same pin.

### Choosing by use case

| What the external instrument expects | Where to wire it |
|---|---|
| Analog edge / level / ramp | **AO ch2** (already reserved); pulse is encoded directly in the AO waveform |
| TTL pulse with a well-defined edge | **TMR0..3** (hardware-paced, ns-scale edges) |
| TTL level without strict timing (e.g. "turn the instrument on for the duration of the scan") | A DIO line (software-paced is fine) |

If the trigger needs to be **synchronous with a specific point in the
experiment** (for example, the moment an iso plateau begins), use AO
ch2: the edge in the AO buffer lands on the pin at exactly the same
time the heater current reaches the corresponding sample, because
both are driven by the same AO pacer clock.

## Caveat: shared start != shared clock

AO and AI on the 2637 have **independent pacer clocks** (XAPCR / XDPCR,
[usb-2637-vs-2627.md](usb-2637-vs-2627.md), lines 117-127). TTLTRG
gives them a common start, but **not** a common clock -- their phases
drift over time as the two pacer clocks differ in their nominal rate.
If you need clock-level synchrony (not just a shared t=0), TTLTRG
alone does not solve it; you must physically tie XAPCR to XDPCR with
a wire.
