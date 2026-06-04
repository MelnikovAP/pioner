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
  | AI ch0    | 0       | Heater current (shunt voltage)                                |
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

The total duration must be a whole number of seconds (software simplification
documented at `pioner.back.modes._validate_programs`).

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
**100 tests, ~30 seconds** locally.

---

## 9. Outstanding work / known limitations

* **Profile duration must be an integer number of seconds.** This is a
  software constraint imposed by the 1-second AI buffer. Lifting it
  requires a small refactor in `ExperimentManager._collect_finite_ai`
  (allocate a sub-second tail buffer for the last fractional second).
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
  `run()`), not the legacy `arm_fast_heat` Tango command. Iso runs stream
  live against the persistent ring buffer; fast/slow still pause the live
  stream for the run's duration (see `docs/live-streaming.md`). A dedicated
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

See `docs/source/` for the long-form architecture notes and the
Sphinx-built API reference under `docs/build/`. The detailed
back-end / pipeline / open-tasks reference lives in `spec.md` and
`todo.md` at the repo root.
