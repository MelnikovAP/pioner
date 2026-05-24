# Known issues

A running log of correctness, stability, and reliability issues observed in
the PIONER codebase (mainline and IR branch). Each entry: symptom, where it
lives, root cause, what is known to work around it, open questions.

---

## 1. FIFO overrun on fast-heat acquisition (legacy `CONTINUOUS` AI path)

### Symptom

A fast-heat run aborts mid-scan with:

```
ULError.OVERRUN: FIFO overrun, data was not transferred from device fast enough
```

Stack trace from the original failing run (operator log):

```
File ".../fastheat.py", line 256, in <module>
    fh.run()
File ".../fastheat.py", line 110, in run
    em.ai_continuous(self._ai_channels, do_save_data=True)
File ".../pioner/back/experiment_manager.py", line 186, in ai_continuous
    self._read_data_loop(do_save_data)
File ".../pioner/back/experiment_manager.py", line 243, in _read_data_loop
    ai_status, ai_transfer_status = self._ai_device_handler.status()
File ".../pioner/back/ai_device.py", line 141, in status
    return self._ai_device.get_scan_status()
File ".../uldaq/ai_device.py", line 210, in get_scan_status
    raise ULException(err)
```

Reproducer (operator's environment): AI base rate 20 kHz, single channel
program with a 3000 ms profile shaped roughly `0, 0, 5, 5, 0, 0` V on AO ch1.

Operator notes:
- Crashes consistently after a single short run on the legacy code path.
- Crashes are noticeably worse under a VM (USB pass-through tax).
- Switching the legacy code to `ScanOption.DEFAULTIO` removed the crash.
- An earlier workaround had been to reset the DAQ memory between runs.
- The same operator reports that "switching from single-ended to default"
  input mode also helped, though the *current* IR-branch config still
  declares `InputMode: 2` (= `SINGLE_ENDED`); see TODO at the end of this
  entry.

### Affected code

The failing stack trace points to `/home/pioner/pivo/try/...` -- a working
copy on the lab machine (Linux host, user `pioner`) that predates both the
mainline rewrite and the IR-branch rewrite. It contains a `fastheat.py`
plus a `pioner/back/experiment_manager.py` with `ai_continuous` and
`_read_data_loop` methods. Neither file layout exists in this repository:

- `src/pioner/back/fastheat.py` is the mainline rewrite (no
  `ai_continuous`, no `_read_data_loop`).
- `pioner-IR-branch/` removed `fastheat.py` entirely; its replacement is
  the `_run_finite_profile` method inside
  `pioner_app/core/experiment_manager.py`.

Where the equivalent code lives now:

| Concept                           | Pre-IR (failing)                                        | IR branch (current)                                                  |
|-----------------------------------|---------------------------------------------------------|----------------------------------------------------------------------|
| Fast-heat entry                   | `fastheat.py::FastHeat.run` -> `em.ai_continuous(...)`  | `daq_controller.run_fast_heat_profile` -> `ExperimentManager._run_finite_profile` ([experiment_manager.py:420](pioner-IR-branch/pioner_app/core/experiment_manager.py#L420)) |
| AI scan option                    | `ScanOption.CONTINUOUS` (drained in a Python loop)      | `ScanOption.DEFAULTIO` ([ai_device.py:251](pioner-IR-branch/pioner_app/hardware/ai_device.py#L251)) |
| Host buffer size                  | Smaller than full scan; read-and-recycle while scanning | Sized to the full scan length (`samples = duration * sample_rate`)  |
| Data read cadence                 | Per-chunk reads inside `_read_data_loop`, with optional simultaneous HDF5 save (`do_save_data=True`) | Single read at end, after `ScanStatus.IDLE` ([experiment_manager.py:461](pioner-IR-branch/pioner_app/core/experiment_manager.py#L461)) |

The pre-IR `ai_continuous` / `_read_data_loop` methods are not present in
the IR branch at all -- they were removed in the rewrite that introduced
`_run_finite_profile`.

### Root cause

`ULError.OVERRUN` is raised by the DAQ driver when samples accumulate in
the device's on-board FIFO faster than the host can drain them. The FIFO
is fixed-size hardware on the DAQ; once full, new samples have nowhere to
go and the scan errors out.

Three factors stacked up on the legacy path:

1. **`CONTINUOUS` scan + active Python consumer.** The AI scan was armed
   with `ScanOption.CONTINUOUS` and the host had to keep up by polling
   `get_scan_status()` and reading chunks out of a ring buffer in
   `_read_data_loop`. Any time the Python loop blocked (GC pause,
   scheduling, disk I/O), the device FIFO kept filling, and once it
   wrapped the driver raised OVERRUN.
2. **Simultaneous HDF5 write (`do_save_data=True`).** The same loop was
   writing each drained chunk to disk via pandas `to_hdf`. HDF5 writes are
   slow (table-format index updates, pickle serialisation) and bursty, so
   the consumer fell behind exactly when the producer needed it most.
   This is the most likely trigger for the specific run logged above.
3. **VM USB pass-through latency.** When the host is a virtual machine,
   USB pass-through adds non-trivial latency to every DMA completion
   delivered from the DAQ. The driver still issues bulk reads, but the
   time between "FIFO has data" and "host process gets it" is longer than
   on bare metal, so the FIFO has less headroom before it overflows.

In short: the producer was hardware-paced at 20 kHz x N channels and the
consumer was Python + disk I/O on a possibly virtualised USB host. The
math does not work.

### Why the IR-branch workaround works

`ExperimentManager._run_finite_profile` in the IR branch eliminates the
streaming-consumer problem entirely:

- AI is armed with `ScanOption.DEFAULTIO`, i.e. a *single-shot finite
  scan*. The DAQ knows exactly how many samples to acquire and stops on
  its own at the end.
- The host buffer is sized to the **full scan length**
  (`samples_per_channel = duration_s * sample_rate`). The DAQ DMAs samples
  directly into that buffer; no wrap-around is needed during the run.
- During the scan the Python loop only polls progress for the UI bar; it
  does **not** read or copy data, and it does **not** write to disk.
- After `ScanStatus.IDLE`, the buffer is read once
  ([experiment_manager.py:461](pioner-IR-branch/pioner_app/core/experiment_manager.py#L461)),
  reshaped, and returned to the caller. Save-to-disk happens after that,
  off the critical path.

This swaps "host must keep up in real time" for "host must allocate enough
RAM up-front". For 20 kHz x 6 channels x 3 s that is ~360 k float samples
= ~2.9 MB -- trivial.

The trade-off: scan length is now bounded by what `create_float_buffer`
can allocate, and the run can only be cancelled at one-second granularity
(the progress poll interval is `time.sleep(0.02)` but the device cannot
be told to stop early without losing the in-flight buffer). Acceptable
for fast-heat single-shot profiles; not acceptable for long iso runs --
the IR branch never tried to use this code path for iso.

### Contributing factors and remaining exposure

- The IR branch's *live signals* and *slow-heat* paths still arm AI with
  `ScanOption.CONTINUOUS`
  ([ai_device.py:255](pioner-IR-branch/pioner_app/hardware/ai_device.py#L255),
  used by `start_continuous` and the slow-heat `start_acquisition`). They
  are subject to the same OVERRUN class of failure if the consuming
  widget falls behind, especially at high sample rates or under VMs.
  In practice this has not been reported because:
  - the live signals widget reads relatively rarely (~1 Hz),
  - the slow-heat widget reads at 100 ms cadence,
  - neither writes data to disk inside the read loop.
- Mainline `src/pioner/back/experiment_manager.py::finite_scan` arms AI
  as `CONTINUOUS` with a *one-second* buffer and uses a half-buffer flip
  protocol to copy data out as the scan progresses
  ([experiment_manager.py:192](src/pioner/back/experiment_manager.py#L192),
  `_collect_finite_ai`). That is closer to the failing legacy approach
  than to the IR-branch fix. It works in the lab today but the same
  OVERRUN risk applies if the half-buffer reader is delayed (GC, disk,
  VM USB latency). See TODO below.

### Workarounds operators have used

- Switch to `ScanOption.DEFAULTIO` and a full-scan host buffer (the IR
  branch's current state, recommended).
- Reset the DAQ between runs (legacy emergency only; does not address the
  cause, only clears state after a crash).
- Run on bare metal rather than a VM; if a VM is unavoidable, prefer a
  hypervisor with USB 2.0 pass-through over USB 3.0 emulation, and pin
  the VM's USB controller to the physical port.

### TODO / open questions

- [ ] **Resolved direction for "single-ended -> default".** The lab board
  is USB-2637, which has **no differential mode** -- only 64 SE inputs
  per the datasheet (specs/USB-2637.pdf). So "default" cannot have meant
  `AiInputMode.DIFFERENTIAL`. It almost certainly meant `ScanOption.DEFAULTIO`
  (the scan option change that this entry documents). The original memory
  conflated the scan-option fix with an input-mode flip that the hardware
  doesn't even support. Worth confirming with the operator, but treat
  the input-mode angle as a dead lead. The IR-branch config still ships
  `InputMode: 2` (= `SINGLE_ENDED`, confirmed via
  `uldaq.ul_enums.AiInputMode`), which matches the only mode USB-2637
  supports. Worth one quick check with the operator to confirm the
  fix was the scan-option change.
- [ ] **Quantify the OVERRUN margin for mainline `finite_scan`.** The
  one-second buffer + half-flip protocol in
  [src/pioner/back/experiment_manager.py:344](src/pioner/back/experiment_manager.py#L344)
  is the same class of design as the failing legacy path, just with a
  larger buffer. Reproduce the failing run on mainline at 20 kHz x 6 ch
  x 3 s (bare metal and VM) and confirm whether mainline is safe or
  whether it should also adopt the IR-branch full-buffer approach.
- [x] **Document USB-2637 FIFO depth.** Resolved: per
  [specs/USB-2637.pdf](specs/USB-2637.pdf) chapter 5 "Memory" table:
  **Data FIFO = 4 kS analog input / 2 kS analog output**. At our typical
  6 channels x 20 kHz aggregate rate (120 kS/s), the AI FIFO fills in
  4096 / 120000 = **~34 ms**. That is the upper bound on host stall time
  before `ULError.OVERRUN` triggers under the legacy CONTINUOUS+HDF5
  path. See [docs/usb-2637-vs-2627.md](docs/usb-2637-vs-2627.md) for
  more headroom calculations. DMA block layout is still undocumented
  in the user's guide; that part remains open and would have to be
  measured empirically.
- [ ] **Decide whether the live-signals / slow-heat `CONTINUOUS` paths
  in IR-branch need the same treatment.** They have not crashed in
  practice but the design is theoretically exposed; either accept the
  risk and document the sample-rate ceiling, or refactor to a finite
  buffered approach.
- [ ] **Investigate whether DMA block size differs between `DEFAULTIO`
  and `CONTINUOUS` in uldaq.** Part of the IR-branch fix may be that
  `DEFAULTIO` issues larger DMA transfers (one per scan rather than per
  chunk), which would reduce per-transfer overhead and increase the
  effective drain rate, independently of the consumer-loop argument
  above. Not verified.
