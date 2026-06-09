# PIONER Lab

> Platform for Integrated Operative Nano Experiments and Research (former *Nanocal*).

PIONER drives MCC USB-DAQ boards to perform single-chip nanocalorimetry on
microgram samples. The codebase covers three experimental modes — *fast*,
*slow*, *iso* — and a Qt5 GUI / Tango server for remote control.

---

## 1. Hardware overview

* **DAQ board:** MCC **USB-2637** (USB-2600 series, 16-bit, 1 MS/s,
  64 single-ended AI channels, 4 AO channels at +/-10 V), driven via the
  [`uldaq` Python bindings](https://files.digilent.com/manuals/UL-Linux/python/index.html).
  Datasheet: [specs/USB-2637.pdf](specs/USB-2637.pdf). The board uses
  single-ended inputs only; there is no differential mode. AI and AO
  scan pacers are independent (no shared internal clock), so synchronous
  AO+AI start is achieved via the external trigger (TTLTRG), not via a
  common pacer.
* **Wiring (default channel layout):**

  | Direction | Channel | Purpose                                                       |
  |-----------|---------|---------------------------------------------------------------|
  | AO ch0    | 0       | Sample current shunt drive / monitoring bias                  |
  | AO ch1    | 1       | Heater voltage (the temperature program & AC modulation live here) |
  | AO ch2    | 2       | Trigger / gate output                                         |
  | AO ch3    | 3       | Reserved (guard heater)                                       |
  | AI ch0    | 0       | Heater current (voltage proxy; not a calibrated shunt, see P0-3) |
  | AI ch1    | 1       | Umod — high-gain modulation read-back (gain ≈ 121)            |
  | AI ch3    | 3       | AD595 ambient / cold-junction reference (100 °C/V)            |
  | AI ch4    | 4       | Utpl — standard thermopile (gain ≈ 11)                        |
  | AI ch5    | 5       | Heater voltage feedback                                       |

  Hardware gains and the AD595 correction polynomial are calibrated values;
  see *Calibration* below.

---

## 2. Installation

### 2.1 Quick start (development on macOS / Linux)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -e .[dev]            # core deps + pytest
pip install -e .[gui]            # adds silx + pyqt5
pip install -e .[server]         # adds pytango (Linux + Raspberry Pi)
pip install -e .[hardware]       # adds uldaq python bindings
```

`uldaq` will install on macOS but `import uldaq` raises `OSError` because
`libuldaq.dylib` is not packaged. On any host where the library is missing,
`pioner.back.mock_uldaq` automatically substitutes a pure-Python simulator
(see [Mock backend](#5-mock-daq-backend)).

Launch the single-window GUI (all three modes + live streaming):

```bash
python -m pioner.runUI --mock        # in-process LocalDeviceController (mock DAQ)
python -m pioner.runUI --hardware    # legacy Tango network backend
python -m pioner.runUI               # autodetect (no PyTango -> mock/local)
```

### 2.2 Raspberry Pi (back-end only, no GUI)

The front-end (Qt) and back-end (DAQ + Tango) are intentionally split via
optional-dependency groups. Install only what each host needs:

| Host | Command | Gets |
|------|---------|------|
| **Raspberry Pi** (instrument) | `pip install -e .[hardware,server]` | uldaq + pytango, no Qt |
| **Laptop / workstation** (GUI) | `pip install -e .[gui,server]` | pyqt5 + silx + pytango, no uldaq |
| **Dev machine** (all + tests) | `pip install -e .[hardware,gui,server,dev]` | everything |

`pyqt5` / `silx` are never pulled in on the Pi with this install. The
`src/pioner/front/` source directory is present on disk (it comes with
`git clone`) but nothing imports it unless `runUI.py` is invoked explicitly —
which will fail with `ImportError` on the Pi, as expected.

**System packages (Pi, one-time).**
Build `libuldaq` from source before `pip install -e .[hardware]`:

```bash
sudo apt install gcc g++ make libusb-1.0-0-dev
wget https://github.com/mccdaq/uldaq/releases/download/v1.2.1/libuldaq-1.2.1.tar.bz2
tar -xvjf libuldaq-1.2.1.tar.bz2
cd libuldaq-1.2.1 && ./configure && make && sudo make install
```

After that, clone the repo on the Pi and install:

```bash
git clone <repo-url> pioner
cd pioner
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -e .[hardware,server]
```

Verify DAQ is visible (USB-2637 must be connected and powered):

```bash
python -c "import uldaq; print(uldaq.get_daq_device_inventory(uldaq.InterfaceType.USB))"
```

Run the back-end smoke check (no hardware needed, uses mock):

```bash
python -m pioner.back.debug
```

For the first end-to-end run against a real USB-2637 board, follow the
operator checklist in [docs/hardware-bringup.md](docs/hardware-bringup.md)
(required settings, real-vs-mock status readout, and the P0-5 trigger
loopback). Each live-board step is a HARD STOP.

### 2.3 Compatibility notes

* Python 3.11 is the supported target. 3.10 and 3.12 also build.
* `uldaq` 1.2.3 (Nov-2021) is the latest upstream release; it ships wheels
  for cp36–cp311. On Python 3.12+, building from source may be required.
* `pytango ≥ 10` ships precompiled wheels for Linux/macOS; building from
  source is rarely necessary.

---

## 3. Three calorimetry modes

For µg samples on a thin-film chip the heat capacity signal is tiny: in pure
DC heating the AC noise of the front-end masks the signal entirely. We
therefore run two distinct families of experiment:

| Mode | Heating rate | Modulation | Signal extracted | Implementation |
|------|--------------|------------|------------------|----------------|
| **fast** | > 1000 K/s (ballistic) | none | direct T(t), enthalpy from area | `pioner.back.modes.FastHeat` |
| **slow** | 0.01 – 10 K/s | AC sine on heater | C_p(T) via lock-in | `pioner.back.modes.SlowMode` |
| **iso**  | constant T   | AC sine on heater | C_p(T) at one point | `pioner.back.modes.IsoMode` |

The AC modulation (default 37.5 Hz / 0.1 V from `settings/settings.json`)
puts a small sine wave on top of the slow heater profile. A software lock-in
detector at the modulation frequency recovers the AC temperature amplitude
`ΔT_AC` and the phase lag `φ`. Heat capacity is then

```
C_p(T) ∝ P_AC / (ω · ΔT_AC) · cos φ
```

The lock-in is implemented as a 4th-order Butterworth low-pass applied with
`scipy.signal.sosfiltfilt` (zero phase lag). See `pioner.shared.modulation`.

### 3.1 Picking a mode programmatically

```python
from pioner.back.modes import create_mode
from pioner.back.daq_device import DaqDeviceHandler
from pioner.shared.calibration import Calibration
from pioner.shared.settings import BackSettings
from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH

settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
calibration = Calibration()
calibration.read("./settings/calibration.json")

with DaqDeviceHandler(settings.daq_params) as daq:
    daq.try_connect()

    programs = {
        "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
        "ch1": {"time": [0, 250, 750, 1000], "temp": [0, 200, 200, 0]},
        "ch2": {"time": [0, 1000], "volt": [5, 5]},
    }
    mode = create_mode("fast", daq, settings, calibration, programs)
    mode.arm()
    df = mode.run()  # pandas.DataFrame with engineering-unit columns
```

### 3.2 Program format

Each AO channel program is a dict with:

* `"time"` — list of monotone time points starting at 0 (in **milliseconds**).
* exactly one of `"temp"` (in °C, calibration is applied) or `"volt"` (in V).

The total duration may be any positive value (fractional seconds are allowed):
the AI frame is collected against a one-second buffer and trimmed to
`round(sample_rate * total_s)`. See `pioner.back.modes._validate_programs`.

For the iso mode, the shorthand `{"chN": {"volt": v}}` is also accepted and
gets normalised internally.

---

## 4. AO/AI pipeline

```
                          ┌────────────────────────────┐
   user program (per AO   │ pioner.back.modes.BaseMode │
   channel: time + temp  ─►  validate                  │
   or volt)               │  interpolate onto AO grid  │
                          │  T → V via Calibration     │
                          │  (slow/iso) AC modulation  │
                          └────────────┬───────────────┘
                                       │ voltage_profiles dict
                          ┌────────────▼───────────────┐
                          │ ScanDataGenerator          │
                          │  flatten to interleaved    │
                          │  AO buffer                 │
                          └────────────┬───────────────┘
                                       │
                                       │
              ┌────────────────────────▼─────────────────────────┐
              │ ExperimentManager                                │
              │  ┌───────────┐         ┌────────────┐            │
              │  │AoDevice   │         │AiDevice    │ buffer     │
              │  │ a_out_scan│ paced   │ a_in_scan  │ shared     │
              │  │ BLOCKIO/  │         │ CONTINUOUS │ via DMA    │
              │  │ CONT.     │         │            │            │
              │  └───────────┘         └────────────┘            │
              │       │                       │                  │
              │  finite_scan: collect 0.5s    │                  │
              │  half-buffer chunks until     │                  │
              │  N samples = rate * seconds   │                  │
              │  (no point loss, no double    │                  │
              │  reads)                       │                  │
              │                               │                  │
              │  iso (ring buffer): bg thread │                  │
              │  appends chunks to deque,     │                  │
              │  trim to ring_buffer_seconds  │                  │
              └────────────────┬──────────────┘                  │
                               │ pandas.DataFrame (raw counts)   │
                               │                                 │
                  ┌────────────▼───────────────┐                 │
                  │ apply_calibration          │                 │
                  │  Taux from AD595 (ch3)     │                 │
                  │  T from Utpl  (ch4)        │                 │
                  │  T-hr from Umod (ch1)      │                 │
                  │  Thtr from V/I (ch5,ch0)   │                 │
                  └────────────┬───────────────┘                 │
                               │                                 │
                               │ engineering units +             │
                               │ Uref (AO ch1 trace)             │
                               │                                 │
                  ┌────────────▼───────────────┐                 │
                  │ Lock-in (slow/iso only)    │                 │
                  │  IQ demod @ f_mod          │                 │
                  │  Butterworth LP 0-phase    │                 │
                  │  amp + phase               │                 │
                  └────────────┬───────────────┘                 │
                               │                                 │
                  ┌────────────▼───────────────┐                 │
                  │ HDF5 (legacy compat)       │ for FastHeat    │
                  │ data/exp_data.h5           │ / SlowMode      │
                  └────────────────────────────┘                 │
                                                                 │
                  GUI receives & plots DataFrame columns ────────┘
```

Buffer-side details:

* The AI buffer is **exactly one second long** (`samples_per_channel =
  sample_rate`). Both halves are filled by the driver in turn; the reader
  detects the half-flip via `current_index` and copies whichever half has
  just become stable. This gives 0.5 s of jitter tolerance for the polling
  thread.
* Both AO and AI scans are stopped explicitly via `scan_stop`. The mock
  backend exposes a `threading.Event`-based stop so the iso ring-buffer
  thread joins cleanly within ~10 ms.
* `_prime_pandas` warms up `to_hdf` once at process start so the first scan
  doesn't lose ~1 second of data to the lazy initialisation of PyTables.

### Constraints & invariants (load-bearing)

These hold across the back-end; breaking one usually produces numbers that
*look* right but aren't (see CLAUDE.md for the full list):

* **AI buffer = exactly one second** (`samples_per_channel = sample_rate`).
  This is the fixed unit the slow/iso half-buffer flip works on. Program
  **duration may be fractional** now (the whole-second `total_ms % 1000 == 0`
  rule was lifted) -- `finite_scan` trims the collected frame to
  `round(sample_rate * seconds)` -- but the buffer itself stays 1 s.
* **Fast-heat uses a single-shot `DEFAULTIO` full-buffer scan** (read once at
  the end, no FIFO overrun); **slow/iso use the `CONTINUOUS` 1 s half-flip**.
* **Sample rate must be even** for the half-flip reshape (the persistent ring
  and slow/iso all use it); the fast single-shot path does not strictly need
  it, but the active rate also feeds the ring, so even is required throughout.
* **Sample rate is per-mode.** `Scan.Sample rate` in `settings.json` is a map
  `{default, fast, slow, iso}` (default 2 kHz monitor, fast 20 kHz, slow/iso
  2 kHz); a bare int still works (same rate for all). Arming a mode applies its
  rate; the GUI's single rate field shows the selected mode's rate and an
  **Apply** press confirms it (arming is blocked until then). Odd or
  sub-Nyquist (`rate <= 2*f_mod`) rates are rejected.
* **AO and AI MUST share one sample rate / clock domain** -- they are always
  set equal; the pipeline assumes a single clock, so an AO != AI rate is a bug,
  not a supported configuration. Any rate change sets both at once.
* **Lock-in needs `f_mod < sample_rate / 2`**; iso replays a 1 s AO buffer
  CONTINUOUS, so `f_mod` should give an integer number of cycles per second to
  avoid a phase jump at the wrap (37.5 Hz does not -- a known WARNING).
* **Safe-voltage clamp**: heater drive is clipped to `[0, safe_voltage]`
  (default 9 V); the heater is driven to **0 V on Off / disconnect / abort**
  (`zero_ao`) so it is never left latched (the DAC holds its last sample).
* **`Thtr` is NaN at idle** (heater current ~ 0) rather than a divide-by-zero
  sentinel; `Uref` is tiled to the AI length for CONTINUOUS / iso.
* **Start order is AI then AO** so the AO leading edge is not missed (without a
  hardware trigger there is a small ~100 us start skew -- todo P0-5).

---

## 5. Mock DAQ backend

`pioner.back.mock_uldaq` is a drop-in replacement for `uldaq`. It is used
automatically when the real driver is missing.

* Same class hierarchy: `DaqDevice`, `AiDevice`, `AoDevice`, `Range`,
  `ScanOption`, …
* Buffer is **not** copied: the mock's worker thread mutates the very list
  passed to `a_in_scan` so existing callers that read the buffer in-place
  continue to work.
* `current_scan_count` and `current_index` advance with wall-clock time so
  the half-buffer reader actually flips.
* AI samples are synthesised from the latest AO voltage on the same channel
  (small additive deterministic noise). Channel layout matches the real
  hardware (see *Calibration*).
* No security theatre, no rate limiting, no session tokens. `disconnect`,
  `release`, `reset` are simple state changes.

This makes development on macOS realistic enough to exercise the entire AO
→ AI → calibration → lock-in pipeline; the test suite under `tests/` does
exactly that.

---

## 6. Calibration

Two calibration JSON files live under `settings/`:

* `default_calibration.json` — identity calibration (V == V, T == T).
* `calibration.json` — chip-specific coefficients (filled in via the GUI).

Beyond the historical `Theater`/`Thtr`/`Ttpl` polynomials, the calibration
JSON now carries an explicit **Hardware** sub-block describing the analog
front-end:

```json
"Hardware": {
  "Gain Utpl": 11.0,
  "Gain Umod": 121.0,
  "AD595 low correction": [2.6843, 1.2709, 0.0042867, 3.4944e-05]
}
```

These were previously hard-coded inside `_apply_calibration`. The block is
optional — falling back to the historical defaults when absent.

### Round trip (T ⇄ V)

`pioner.shared.utils.temperature_to_voltage` is fully vectorised
(`np.searchsorted`) and tolerates small sub-zero dips of the heater
polynomial near `V = 0` (production sensors have one); only catastrophic
non-monotonicity (overall decreasing trend) is rejected.

---

## 7. Tango server

```bash
python -m pioner.back.nanocontrol_tango NanoControl
```

Public commands:

| Command            | Description                                   |
|--------------------|-----------------------------------------------|
| `set_connection`   | Open the USB connection to the DAQ board      |
| `disconnect`       | Release the DAQ board                         |
| `apply_default_calibration` / `apply_calibration` | Load calibration from disk |
| `select_mode("fast"/"slow"/"iso")` | Pick the mode for the next arm/run |
| `arm(programs_json)` | Validate + build profiles for the selected mode |
| `run`              | Execute the armed mode                        |
| `arm_fast_heat`, `run_fast_heat`, `arm_iso_mode`, `run_iso_mode` | Legacy shortcuts |

---

## 8. Tests

```bash
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

The suite covers calibration round-trip, T↔V vectorised conversion,
modulation/lock-in (including FFT integer-cycle window and AO period
integrity), the mock DAQ contract, the post-processing edge cases
in `apply_calibration` (Uref tiling, Thtr-NaN, Rhtr units regression),
and an end-to-end pass through all three modes on the mock backend
including the hardware-trigger path. It also pins the default-calibration
identity constants (`tests/test_calibration.py`, todo P2-21) and round-trips
the settings-driven `HardwareTrigger` flag (`tests/test_back_settings.py`).
**186 tests, ~45 seconds** locally.

---

## 9. Outstanding work / known limitations

* **AO/AI start skew.** By default the two scans are armed sequentially
  (AI first, then AO, so no leading AO edge is missed) with a few ms
  between starts; for the 1000+ K/s fast mode the leading 1-2 ms of the
  trace is therefore not perfectly aligned. A hardware-trigger path exists
  (`DaqParams.hardware_trigger`, default off): both scans pre-arm with
  `ScanOption.EXTTRIGGER` and a single `fire_software_trigger` releases
  them on a shared t=0. It is now settings-driven -- set
  `DAQ.HardwareTrigger: true` in `settings.json` to enable it without a code
  edit. It is mock-tested; real-hardware loopback validation is still pending
  (todo P0-5, see [docs/hardware-bringup.md](docs/hardware-bringup.md)).
* **GUI mode selection (fast / slow / iso).** The main window has a
  `Mode` combo: fast and slow share the ramp-table editor (slow layers AC
  modulation in the backend), iso uses the Set/Off controls. The GUI talks
  to the instrument through a `DeviceController` (`arm(mode_name, ...)` /
  `run()`), not the legacy `arm_fast_heat` Tango command. **Iso "Set" holds
  the setpoint indefinitely** (non-blocking; `start_iso_hold`) until "Off",
  or — with a duration in the iso panel — runs a timed program that
  auto-returns the heater to 0 V after N seconds. Iso streams live against the
  persistent ring buffer; fast/slow still pause the live stream for the run's
  duration (see `docs/live-streaming.md`). A dedicated
  CalibrationMode is not yet a run mode (todo P1-22).
* **Mock data is not a thermal model.** The synthetic AI signal mirrors the
  AO voltage scaled by hand-picked constants. It is sufficient for
  pipeline shape validation, not for closed-loop control development.
* **`Thtr` is NaN whenever the heater current is below ~1 nA.** Earlier
  versions emitted a sentinel of around –1070 °C in those samples. If you
  re-process old HDF5 files, drop the rows with `np.isfinite(Thtr)` first.
* **`Uref` reflects the actual commanded voltage**: for iso (CONTINUOUS
  AO) the per-second AO buffer is tiled to match the AI length, so the
  column is meaningful for the full duration of an iso run.

---

## 10. Project layout & open-source separation

```
src/pioner/
  back/    DAQ + acquisition + experiment modes (talks to uldaq / mock)
  front/   Qt single-window GUI (optional; only loaded by runUI)
  shared/  calibration, channels, modulation, settings, constants
settings/  runtime config + calibration JSON (settings.json, calibration.json, ...)
data/      HDF5 working files (see "Data files" below)
specs/     MCC board datasheets (USB-2637 etc.)
docs/      reference library + Sphinx site (docs/source/)
postmortem/  resolved-incident write-ups (indexed by ERRORS.md)
```

The back-end is deliberately instrument-agnostic where it can be: the DAQ
device handling, the mock backend, channel/range/sample-rate configuration,
and the acquisition/streaming layer do not depend on any nanocalorimeter
specifics. There is an active plan to split these into a reusable open-source
DAQ library, leaving the chip-specific calibration / modes / lock-in as the
proprietary layer — see **[pioner-pypi.md](pioner-pypi.md)** for the verified
boundary and migration plan.

## 11. Data files

`data/` holds HDF5 working files written by runs (not reference fixtures):

* `data/exp_data.h5` — last experiment result in **engineering units (T)**
  (fast/slow/iso); the GUI/Tango download path and the legacy facades write here.
  `DeviceController.run()` returns a `RunResult` (file paths + summary, **not** an
  in-RAM frame); the GUI reads this file back **decimated** for the plot
  (`modes.read_calibrated_h5`), so a long run never loads wholly into memory.
* `data/exp_data_raw.h5` — **raw AI (U, ADC volts)** streamed straight to disk by
  the `DiskRecorder` during a slow off-ring run, then calibrated into
  `exp_data.h5` by `modes.finalize_raw_to_h5` (chunked, flat memory). Kept for
  re-calibration.
* `data/raw_data.h5` (+ `data/raw_data/`) — raw AI buffer dumps from the
  acquisition layer.

These are runtime artefacts; a run overwrites `exp_data.h5` (and
`exp_data_raw.h5`), so restore them from git if you clobbered a reference scan.

## 12. Documentation map

* **[README.md](README.md)** — this file: current state, how to run.
* **[TODO.md](TODO.md)** — forward-looking roadmap (back / front / hardware /
  open-source split).
* **[ERRORS.md](ERRORS.md)** + `postmortem/` — resolved incidents, chronological.
* **[pioner-pypi.md](pioner-pypi.md)** — open-source / proprietary split plan.
* **docs/** — reference library: [docs/pipeline.md](docs/pipeline.md) (full
  AO/AI pipeline spec), [docs/mock-verification.md](docs/mock-verification.md),
  [docs/design-notes.md](docs/design-notes.md),
  [docs/hardware-bringup.md](docs/hardware-bringup.md),
  [docs/modulation.md](docs/modulation.md),
  [docs/live-streaming.md](docs/live-streaming.md),
  [docs/Martin-calibration-procedure.md](docs/Martin-calibration-procedure.md),
  and the Sphinx API site under `docs/source/` (built to `docs/build/`).

## License

See [LICENSE](LICENSE).
