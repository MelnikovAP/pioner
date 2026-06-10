# Bondar uCal — analytical reference

This document summarises the legacy C++ Borland C++ Builder project that
shipped with the previous-generation uCal nanocalorimeter (referred to here
as **Bondar uCal**) and contrasts it with the current Python pipeline in
`src/pioner/`. All claims are verified against the actual source under
`Bondar-uCal/uCal/`. Where a claim is an inference (not directly visible in
the code) it is explicitly marked **[INFER]** with the reasoning.

The C++ tree must not be modified (read-only reference). Two folders
exist: `uCal/` (newer, has Telnet remote control = Unit12 + version 1.3.0.1)
and `uCal_/` (older). Diff between them is small: only `Unit1.{cpp,h}`,
`Unit2.cpp`, `Unit4.{cpp,h}`, `NanoCalorimeter.cpp` differ, plus Unit12
present only in `uCal/`. **All file references below point to `uCal/`**.

Title strings: `ABOUT1 "Version 1.3.0.1  10.07.2011"`, `ABOUT2 "(c) A.Bondar
2006-2011"` ([uCal/Unit1.cpp:5-6]). So the code base is from 2006–2011, the
remote-control variant from ~mid-2011.

---

## 1. Top-level architecture

* **GUI framework**: VCL (Borland C++ Builder 5/6 era).
  `NanoCalorimeter.cpp` is the entry point; `WinMain` instantiates 9
  forms ([uCal/NanoCalorimeter.cpp:21-42]).
* **DAQ vendor**: IOtech via `DAQX.DLL` + `Daqx.h` API. The bundled
  `DaqRoutines.cpp` enumerates IOtech device families
  (`DaqBook2000A/E/2001/2005/2020`, `DaqBoard1000/1005/500/505`,
  `DaqScan2000`, `DaqLab2000`) — i.e. *not* the Measurement-Computing
  USB-2627/2637 used today. The whole driver layer (`daqAdc*`,
  `daqDac*`, `daqIOWrite`, `daqWaitForEvent`) is IOtech-specific
  ([uCal/INCLUDE/DaqRoutines.cpp:46-69]).
* **Threading**: two TThread subclasses, `TSineGen` ([uCal/Unit6.cpp:38])
  and `GetData` ([uCal/Unit7.cpp:25]), both `FreeOnTerminate=true`,
  share a single `CRITICAL_SECTION CS` exposed on `Form1`
  ([uCal/Unit1.cpp:319]). All UI control runs on the main thread via
  three VCL `TTimer`s: `Timer1` (continuous-monitor polling, period set
  from `Edit11`), `Timer3` (post-acquisition demod), `Timer4` (sweep
  step driver).
* **Persistence**: text files everywhere. Calibration: INI
  (`DATA/calibration.ini` etc., via `TIniFile`). Setup: INI
  (`setup.ini`, `main.ini`). Measurement: plain TXT with header lines
  (`*** data type N ***`). No HDF5, no JSON.
* **License gate**: `CheckS` ([uCal/Unit1.cpp:3206-3234]) does an XOR /
  `_crotr` rotation against the device serial returned by
  `daqGetDeviceList` ([uCal/Unit1.cpp:1606-1612]) and compares against
  `HWcode1/HWcode2` stored in `main.ini`. Failure shows the `Registr`
  form (Unit5) which expects an unlock password `"kolbasa"`
  ([uCal/Unit5.cpp:30-40]). Irrelevant to the physics but explains why
  the older app rejects a fresh DAQ board.

---

## 2. File-by-file reference

### 2.1 [uCal/NanoCalorimeter.cpp](../Bondar-uCal/uCal/NanoCalorimeter.cpp)
Borland-generated entry point. `WinMain` creates the 9 forms (`TForm1`
... `TFormLock`, `TRegistr`) and enters the message loop. No business
logic.

### 2.2 [uCal/Unit1.{h,cpp}](../Bondar-uCal/uCal/Unit1.cpp) — main form

3528 lines. Contains nearly everything: globals, INI I/O,
calibration, hardware open/close, AI/AO orchestration, lock-in
(`CalcAF`), all GUI callbacks. Acts as a god-object.

Header `Unit1.h` declarations of note:

```cpp
#define MAXCHANCOUNT 5     // physical AI count actually used
#define MAXBUFFER    100000
#define MULTSIZE     100000
#define MAXDATABUFF  100000

typedef struct { float time, amplitude, phase, Ttpl, Uhtr,
    Ihtr, Thtr, Thtrd, Taux, frequency, famplitude, foffset,
    R1htr, power; } ND_DATA;     // 14 floats per scalar measurement

enum grapht { xDisabled, xTm, xiT, xiTd, xeT, xU, xFr, xAm, xOff,
    xFastt, xFasttem, cTThtr, cTThtrd, cThtrUh, cThtrdUh, cThtrUt,
    cThtrdUt, cAThtr, cAThtrd };   // X-axis view selector for Form4
```

Critical Unit1.cpp constants and globals (all module-scope, lines
[32-110]):

| Name | Default | Meaning |
| --- | --- | --- |
| `chancount` | 5 | active AI channel count |
| `buffsize` | up to `MAXBUFFER` | samples per AI scan |
| `bufferin[MAXBUFFER*5]` | raw 16-bit AI samples |
| `ADCdata[5][MAXBUFFER]` | post-scaled AI in volts |
| `ADCdata4disp[5][MAXBUFFER]` | snapshot for the scope window |
| `PulseRef[MAXBUFFER]` | copy of ch0 during a fast pulse |
| `mult[MULTSIZE]` | lock-in correlator output |
| `resultdata[MAXDATABUFF]` | logged `ND_DATA` records (1e5 max) |
| `gainlist[7]` | `{1,2,5,10,20,50,100}` AI PGA gains |
| `heatersafeV` | 5.61 V | clamp applied in `SetHeater` |
| `Kadapt` | 1.0 | adaptation gain for fast-heat profile |
| `ADclck` | 10000 Hz initial | AI sample rate |
| `GenMode` | 0/1/2/3/4 | off/cont/freqsweep/amplsweep/offsetsweep |

Function map (top-to-bottom):

| Line | Function | Role |
| --- | --- | --- |
| 137 | `ErrorHandler` | DAQ error callback |
| 151 | `smartrd` | round-nice plot bounds |
| 163/235 | `ReadIni / WriteIni` | per-experiment setup |
| 302/315 | `WriteMainValues / ReadMainValues` | global path + license codes |
| 329/344 | `ReadMsg / WriteMsg` | lock-screen notes |
| 358/417 | `ReadCalibration / WriteCalibration` | calibration.ini load/save |
| 452 | `SetHeater` | clamp `[0, heatersafeV]`, write to AO1 |
| 477 | `TempRun` | per-tick ramp logic: advance T or V along the ramp, log into `resultdata`, auto-save every 10 min |
| 675 | `intfilter` | symmetric IIR moving average |
| 701 | `median` | running-window median filter |
| **721** | **`CalcAF`** | **software lock-in (see §6)** |
| 965 | `ShowGenStat` | LED panel for generator state |
| **1041** | **`UnpackData`** | **raw AI -> engineering units (see §5.3)** |
| 1401 | `DrawData` | scope plot |
| 1494 | `SineGen` | start `TSineGen` thread |
| 1526 | `ADCscanrate` | set AI rate via `daqAdcSetRate`, clamp [100, 1e6] |
| 1549 | `OutDigPort` | DIO write (8255 port A) — unused by default flow |
| 1559 | `VoltGen` | static AO write: `iampl = 65535 * (volt+10) / 20` |
| 1571 | `openDEV` | open device, configure AI channel list and gains |
| 1636 | `transfer_n_display` | launch `GetData` thread for one finite acquisition |
| 1657/1779/1899/2020 | `sweep_f / sweep_a / sweep_o / sweep_af` | freq / amp / offset / generic sweep step engines |
| **2273** | **`fastheatrun`** | **NShot AI acquisition with hardware switch on AO2 (see §5.4)** |
| 2484 | `SetTemp` | snapshot start values into UI |
| 2737 | `Snapshotsignal` | dump per-sample `Ref, Umod, Utpl, Uhtr` to `signal<timestamp>.txt` |
| 2929 | `disperror` | 7-LED bar for live `T_chip - (Ttpl+Taux)` mismatch |
| **3148** | **`TempToVoltage`** | Newton iteration that inverts `VoltageToTemp` (target tol 5 mK) |
| **3170** | **`VoltageToTemp`** | cubic: `itk2*v + itk3*v^2 + itk4*v^3`, clamped >=0 |
| 3206 | `CheckS` | hardware-serial license check |
| 3243/3263 | `switch2pulse / switch2modulation` | UI-only mode flags (`fastheating=true/false`). They do *not* drive hardware on their own; the actual switch is via `VoltGen(2, 4.5/0)` inside `fastheatrun` and via `pulseshoot` / `SineGen` issuing AO config. |
| 3460 | `wait_finish` | poll `SineGenRun/GetRun` up to 10 s |
| 3492 | `Init_Grid` | zero the fast-heat StringGrid |

### 2.3 [uCal/Unit2.{cpp,h}](../Bondar-uCal/uCal/Unit2.cpp)
About box (`TForm_About`). Pure cosmetics: layered-window fade in/out
animations, "Alt" hotkey shows the Registr form
([uCal/Unit2.cpp:26-29]). No physics.

### 2.4 [uCal/Unit3.{cpp,h}](../Bondar-uCal/uCal/Unit3.cpp)
Scope window (`TForm3`). Three `TTrackBar`s drive `dxscale`, `dxshift`,
`dyscale` via `recalcsc()` ([uCal/Unit3.cpp:24-30]). Five check-boxes
select which AI channel to draw. `BitBtn1Click` sets the global
`DoSnapshot = true`, picked up by `UnpackData -> Snapshotsignal` on the
next acquisition cycle ([uCal/Unit3.cpp:94-97]).

### 2.5 [uCal/Unit4.{cpp,h}](../Bondar-uCal/uCal/Unit4.cpp) — Graph form
3741 lines. The post-processing / plotting / calibration-fit workbench
that owns the saved scans.

Important globals: `int datatype` (1..5 — selects the file header on
save); `int GraphtType` (enum `grapht`); `ND_DATA backup[MAXDATABUFF]`
(undo buffer); `fbuff/fbuff2/xbuff[MAXDATABUFF]` (scratch). `k0..k3`
hold the current fit coefficients (filled by `BitBtn8Click` and pushed
to the Form10 calibration fields by `BitBtn9Click`).

| Line | Function | Role |
| --- | --- | --- |
| 85 | `avg_power` | running average of `R1htr * (peak²-min²)/4` across `resultdata` |
| 124/515/801/1020 | `DrawGrapht / DrawGraphP / DrawGraphF / DrawGraphC` | the four graph variants |
| **1612** | **`SaveDataTxt`** | TXT writer; the column set depends on `datatype` (see §7) |
| **1690** | **`LoadDataTxt`** | TXT reader; the first line picks the schema |
| 1822 | `RedrawGraph` | top-level repaint coordinator |
| 1888/1939/1986 | `SaveDataJPG / SaveDataBMP / DrawOnBitmap` | screenshot writers |
| **2057** | **`setgraphX`** | dispatch table that wires `GraphtType` to the correct draw routine and to Form4's labels |
| 2545 | `find_index` | x-axis lookup for cursors |
| 2672 | `filter_it` | apply median (`Edit1`) + symmetric MA (`Edit2`) to amplitude/phase/Ttpl/Thtr |
| 2723/2745 | `backup_it / restore_it` | filter undo |
| 2803 | `BitBtn4Click` | linear-baseline subtraction on amplitude+phase (`linflat`) |
| 2997/3010 | `linflat / linflat_m` | baseline removal (slope+offset across endpoints) |
| 3085 | `removexep` | bi-exponential fit + subtract (split at midpoint of Uhtr crossing) |
| 3123 | `fitfallexp` | log-linear fall fit with `vmin` adapted |
| 3172 | `fitriseexp` | log-linear rise fit with `vmax` adapted |
| 3221 | `buildlinearleastsquares` | rotation-stable 2x2 LSQ (also used by exp fits) |
| 3286 | `BitBtn7Click` | invokes `removexep` |
| 3291/3321 | `EnterCview / LeaveCview` | calibration-mode UI lock (`calibrun = true/false`) |
| 3414 | `BitBtn8Click` | **fit a polynomial to the chosen calibration cross-plot** (Taux↔Thtr, Thtr↔Uhtr, etc.) |
| 3572 | `BitBtn9Click` | apply fitted `k0..k3` to the Form10 calibration edit fields (then auto-save) |
| 3643 | `BitBtn10Click` | divide measured amplitude by `acr0+acr1*T+...` to get the AC-corrected response |
| 3682 | `safebuildpoly3` | 2nd-order baseline + 3rd-order residual fit (used in commented-out path) |
| 3698 | `convert_calib` | one-shot legacy-format migration |

### 2.6 [uCal/Unit5.{cpp,h}](../Bondar-uCal/uCal/Unit5.cpp)
`TRegistr` — hardware-license registration. Hidden unlock pwd
`"kolbasa"` reconstructed character-by-character to defeat naive `strings`
([uCal/Unit5.cpp:30-40]). UI lets the user type the serial-derived
`HWcode1/HWcode2`. Persists into `main.ini`.

### 2.7 [uCal/Unit6.{cpp,h}](../Bondar-uCal/uCal/Unit6.cpp)
Two heavy items live here.

* **`TSineGen::Execute`** ([uCal/Unit6.cpp:43-77]) — the continuous AC
  source. Outputs on AO0 with `daqDacSetOutputMode(DdomStaticWave)` +
  `daqDacWaveSetPredefWave(Wform, iampl, ioffset, dcycle, 0)` and
  `DdwmInfinite` mode. While AO0 is running, AO1 and AO2 are pinned to
  their last-set static voltages (`valdaq1`, `valdaq2`). DAC clock:
  `DAclck = Frequency * samples2per` where
  `samples2per = clip(400000/freq, ≤1024)` ([uCal/Unit1.cpp:1502-1503]).
* **`pulseshoot(u0,n1,u1,n2,u2,counts)`** ([uCal/Unit6.cpp:92-170]) —
  the legacy fast-pulse engine. Two shapes are supported:
  * `arbWFmode == true`: copy `AWbuf[]` (built by Unit1::BitBtn10 from a
    user-edited `StringGrid`, or loaded from a TXT by Unit1::BitBtn9)
    directly into `bufferout2`.
  * `arbWFmode == false`: 3-segment step `(u0 [0:n1), u1 [n1:n2),
    u2 [n2:counts))`.

  Each sample is clamped against `heatersafeV` and a warning is shown
  if any exceeds it. The waveform is then armed on AO1 as
  `DdwmNShot, counts` clocked from **`DdcsAdcClock`** —
  i.e. AO1 and AI share the same time base, so the pulse and the
  recorded AI are sample-aligned by construction. AO0 is parked at the
  modulation offset (`Goff`) and AO2 keeps its last value.

### 2.8 [uCal/Unit7.{cpp,h}](../Bondar-uCal/uCal/Unit7.cpp)
`GetData::Execute` — the single-shot AI thread used by everything
except `fastheatrun`. Sequence:
`daqAdcSetScan -> daqAdcSetAcq(DaamNShot) -> ADCscanrate ->
daqSetTriggerEvent(DatsImmediate / DatsScanCount) ->
daqAdcTransferSetBuffer(... DatmUpdateBlock|DatmCycleOff) ->
daqAdcTransferStart -> daqAdcArm -> daqWaitForEvent(DteAdcDone)`
([uCal/Unit7.cpp:39-54]). Blocking; the main thread sees completion
via Timer3 checking `GetRun == 0`.

### 2.9 [uCal/Unit8.{cpp,h}](../Bondar-uCal/uCal/Unit8.cpp)
`TForm8` — data-folder picker. Provides "today's date" template
(`YYYY-MM-DD` or `YYYY-MM-DD-<suffix>`) and writes `setup.ini` into the
target folder ([uCal/Unit8.cpp:86-110]).

### 2.10 [uCal/Unit9.{cpp,h}](../Bondar-uCal/uCal/Unit9.cpp)
`TForm9` — file browser sidebar. Single `TFileListBox`. Clicking a
file calls `LoadDataTxt(filename)`.

### 2.11 [uCal/Unit10.{cpp,h}](../Bondar-uCal/uCal/Unit10.cpp)
`TForm10` — Calibration dialog. 26 `TEdit` controls; the mapping
to coefficient variables is fixed (see §4). `BitBtn3Click` parses the
edits into the C globals and writes `DATA/calibration.ini`;
`BitBtn1Click` does the same plus opens a Save-As dialog
(`WriteOtherCalibration`). The Form4 fit-buttons push their fitted
`k0..k3` into specific `Edit*` controls here ([uCal/Unit4.cpp:3572-3617]
maps each `GraphtType` → which Edit).

### 2.12 [uCal/Unit11.{cpp,h}](../Bondar-uCal/uCal/Unit11.cpp)
`TFormLock` — operator lock screen (memo + unlock button). Re-enables
Form1 and Form10 on dismissal. No physics.

### 2.13 [uCal/Unit12.{cpp,h}](../Bondar-uCal/uCal/Unit12.cpp) (uCal only)
`TFormRemote` — embedded **Telnet server** for remote control.
Default port from `RemotePort`, login/password from `Login/Password`
globals (no encryption). `IdTelnetServer1Execute`
([uCal/Unit12.cpp:71-222]) is the command dispatcher:

* Top-level verbs: `ON, START, SCANCONT, MODCONT, MODOFF, SLOWSET,
  SLOWOFF, FRAMP, ARAMP, ORAMP, FASTLOAD, FASTMAKE, FASTARM, MODPHZERO,
  TERRZERO, LOGFREE, LOGRT, LOGRV, EXIT`. Each is implemented by
  `PostMessage(Form1->ButtonN->Handle, BM_CLICK, 0, 0)` — i.e. the
  server *clicks* buttons on the main form, so the protocol is exactly
  the GUI verb set, nothing more.
* Field setters via `FIXXXXDDDD...`: `SCSR` (scan rate), `SCBS` (buffer
  size), `SCCP` (scan period / Timer1 interval), `MFRS/MFRE` (mod freq
  start/end), `MAMS/MAME` (mod amp start/end), `MOFS/MOFE` (mod offset
  start/end), `RSTP` (sweep steps), `SHST/SHET` (slow-heat start/end
  temp), `SHSV/SHEV` (slow-heat start/end voltage), `SHRT/SHRV`
  (rate per minute, °C/min or V/min).

### 2.14 [uCal/polleastsq.{cpp,h}](../Bondar-uCal/uCal/polleastsq.cpp) + [uCal/sqrless.cpp](../Bondar-uCal/uCal/sqrless.cpp)
Two **independent** polynomial-LSQ implementations of `buildpoly` with
the same signature. `polleastsq` uses the AP library (`ap.h`) and is
the high-quality version (QR-like rotation-stable). `sqrless.cpp`
re-defines the same `buildpoly` via plain Gaussian elimination on the
sums-of-powers normal matrix. Only one is linked at a time. Question
to verify on real binary: which one ships in the .exe? The build file
list in `NanoCalorimeter.cpp` includes `USEUNIT("sqrless.cpp");`
([uCal/NanoCalorimeter.cpp:19]), but `polleastsq.cpp` is *not* in that
USEUNIT list. **[INFER]** `sqrless.cpp` is the production polynomial
fit, `polleastsq.cpp` is dead code kept for reference.

### 2.15 [uCal/INCLUDE/DaqRoutines.cpp](../Bondar-uCal/uCal/INCLUDE/DaqRoutines.cpp)
Thin device-enumeration helper. Walks
`daqGetDeviceList -> daqGetDeviceProperties` to find a compatible
IOtech board. Not used by `Form1::openDEV` directly (it does its own
walk).

### 2.16 [uCal/AP.H](../Bondar-uCal/uCal/AP.H)
Header for the AP (ALGLIB-flavour) math library used by
`polleastsq.cpp`. Not opened in detail.

### 2.17 Binary blobs
`DAQX.DLL` (IOtech driver redist), `msvcr71.dll` (MSVCRT for the
Borland CRT), `LIB/DAQX.lib`, `LIB/BCB5DaqX.lib` (Borland C++ Builder
5 import library). Don't run these against the current hardware.

---

## 3. Hardware mapping (DAC and AI)

### 3.1 DAC layout (verified)

| Logical | Role | Driver | Source |
| --- | --- | --- | --- |
| AO0 | Continuous AC sine generator (predefined wave, infinite mode) | `daqDacSetOutputMode(DdomStaticWave) + daqDacWaveSetPredefWave + DdwmInfinite` | [uCal/Unit6.cpp:54-71] |
| AO1 | Heater drive. Either a static DC level (`SetHeater -> VoltGen(1, V)`) or a finite NShot waveform (`pulseshoot`). When NShot, **clocked from AdcClock** so AO/AI are sample-locked. | [uCal/Unit1.cpp:461], [uCal/Unit6.cpp:151-157] |
| AO2 | "Hardware switch" enable line. Toggles to **4.5 V at the start of `fastheatrun`** and back to 0 V at the end ([uCal/Unit1.cpp:2281, 2300]). **[INFER]** drives an analog relay / FET that gates the heater path into the fast-pulse front-end. The C++ code never reads this signal back; the convention is encoded only in `fastheatrun` and the unconditional `VoltGen(2, 0.0)` calls in `Button1Click` (init) and `Button2Click` (close). |
| AO3 | Unused. Pinned to 0 V on close ([uCal/Unit1.cpp:2187]). |

DAC encoding (`VoltGen`, [uCal/Unit1.cpp:1559-1568]):
`iampl = (DWORD)(65535 * (volt + 10.0) / 20.0)` — unsigned 16-bit on
±10 V; identical for `daqDacWt` paths.

### 3.2 AI layout

`openDEV` ([uCal/Unit1.cpp:1587-1592]) wires logical software channels
0..4 onto physical AI channels {0, 1, 4, 5, 3}:

| Logical (used in `ADCdata[ich]`) | Physical (board) | Label | Notes |
| --- | --- | --- | --- |
| 0 | 0 | `Uref` / shunt voltage | acts as the lock-in **reference** (proxy for heater current). Comment in the code says "Uref" but it is the shunt voltage; after `ihtrk/ihtro` it becomes `Ihtr` in mA. |
| 1 | 1 | `Umod` | high-gain thermopile AC channel. Divided by **121** in `UnpackData` ([uCal/Unit1.cpp:1143]) — this is the IA gain on Umod. |
| 2 | 4 | `Utpl` | standard thermopile DC channel. Divided by **11** ([uCal/Unit1.cpp:1144]). |
| 3 | 5 | `Uhtr` | heater feedback (V across heater + shunt). Multiplied by 1000 only to express in mV ([uCal/Unit1.cpp:1145]). |
| 4 | 3 | `Uaux` | AD595 cold-junction. Scaled by 100 (°C/V) then polynomial-corrected below −12 °C ([uCal/Unit1.cpp:1209-1212]). |

This is the same channel set as the Python pipeline ([src/pioner/shared/channels.py:36-41]) — the physical numbering matches exactly. The Python code re-numbers everything by the physical index (HEATER_CURRENT_AI=0, UMOD_AI=1, AD595_AI=3, UTPL_AI=4, UHTR_AI=5).

PGA gains: per-channel `gains[ich] = (DaqAdcGain)(6 - TrackBarPosition)`
([uCal/Unit1.cpp:2163-2166]); positions 0..6 map onto the
`gainlist = {1, 2, 5, 10, 20, 50, 100}` lookup ([uCal/Unit1.cpp:50,
1066]). Auto-gain logic in `UnpackData` adjusts the TrackBar when the
raw max stays comfortably below 32760 ([uCal/Unit1.cpp:1101-1129]).

Flags: `DafAnalog | DafBipolar | DafSettle5us` by default; the settle
time drops to 1 µs if `ADclck > 1e6/chancount/5 = 200000/5 = 40000`
Hz (off by factor 5 in C++ vs. the 200 kHz comment — see §8).
([uCal/Unit1.cpp:2561-2563])

Sample-rate limits: AI clamped to `[100, 1e6]` Hz inside
`ADCscanrate` ([uCal/Unit1.cpp:1531-1532]). Buffer min 10, max
`MAXBUFFER = 100000` samples ([uCal/Unit1.cpp:2549-2552]).

### 3.3 Digital I/O
`OutDigPort` writes byte `bb` to 8255 Port A
([uCal/Unit1.cpp:1549-1557]). Configured for OUT mode. **[INFER]**
*not used* by any of the main mode paths; grep shows no call from
within `uCal/` cpp files. Probably wiring for an unused signalling
line.

---

## 4. Calibration

### 4.1 Stored coefficients (calibration.ini)

`ReadCalibration` / `WriteCalibration` ([uCal/Unit1.cpp:358-450])
define the schema. Each Form10 `EditN` is bound to one variable:

| INI section / key | Variable | Form10 control | Used in |
| --- | --- | --- | --- |
| `Ttpl/k1x` | `ttplo` | Edit3 | thermopile offset (mV) |
| `Ttpl/k2` | `ttplk` | Edit4 | `Ttpl_°C = ttplk * (Umod+ttplo) + ttplk2 * (Umod+ttplo)^2` |
| `Ttpl/k3` | `ttplk2` | Edit24 | (same) |
| `Thtr/k1` | `thtrk1` | Edit6 | `Thtr = thtrk1 + thtrk2*(R+Rhcorr) + thtrk3*(R+Rhcorr)^2` |
| `Thtr/k2` | `thtrk2` | Edit5 | |
| `Thtr/k3` | `thtrk3` | Edit15 | |
| `Thtr/corr` | `Rhcorr` | (auto, no Edit) | adaptive Δ that snaps Thtr to Ttpl+Taux when `DoRhcorr` ([uCal/Unit1.cpp:1308-1342]) |
| `Thtrd/k1..k3` | `thtrdk1..k3` | Edit17/Edit7/Edit8 | same shape applied to dynamic R |
| `Thtrd/corr` | `Rhdcorr` | (auto) | |
| `Uhtr/k1` | `uhtro` | Edit11 | offset added in mV; used to recover Uhtr-AC drop |
| `Uhtr/k2` | `uhtrk` | Edit12 | gain on the heater feedback chain |
| `Ihtr/k1` | `ihtro` | Edit13 | offset of the Ihtr line (mA) |
| `Ihtr/k2` | `ihtrk` | Edit14 | slope V→mA on the shunt readout |
| `U2T/k4` | `itk4` | Edit18 | cubic `V→T_chip = itk2*V + itk3*V² + itk4*V³` |
| `U2T/k2` | `itk2` | Edit19 | (this is the *direct* heater V→T forward model) |
| `U2T/k3` | `itk3` | Edit20 | |
| `Correction/k1..k4` | `acr0..acr3` | Edit1/Edit21/Edit22/Edit2 | amplitude AC correction polynomial `kamp(T) = acr0 + acr1*T + acr2*T² + acr3*T³`, used as a divisor on the lock-in amplitude |
| `Resistance/R` | `resistance` | Edit23 | fallback heater R if Uabs unavailable |
| `Resistance/SafeV` | `heatersafeV` | Edit25 | clamp ceiling for SetHeater (5.61 V default) |
| `Info/Comment` | (text) | Edit26 | free-form note |

### 4.2 Calibration-fit workflow (Form4 calibration mode)

Each "calibration view" in Form4 (`EnterCview` flips a flag) plots one
cross-relationship and lets the user fit a polynomial. `BitBtn8Click`
([uCal/Unit4.cpp:3414-3569]) populates `xbuff/fbuff` from the chosen
pair, calls `buildpoly(..., m=2 or 3, coef)`, and writes `k0..k3`.
`BitBtn9Click` ([uCal/Unit4.cpp:3572-3618]) then pushes those into the
right `Form10 EditN` and *immediately* calls `Form10->BitBtn3Click` to
persist `DATA/calibration.ini`. Available fits (by `GraphtType`):

* `cTThtr` (k0..k2): `Taux` vs `Thtr` → tunes `thtrk1/k2/k3`
* `cTThtrd`: same on `Thtrd`
* `cThtrUh`: `Thtr-Thtr[0]` vs `Uhtr` → tunes `itk2/k3/k4`
* `cThtrdUh`: same on `Thtrd`
* `cThtrUt`: `Thtr-Taux` vs `Ttpl` → tunes `ttplk/k2`
* `cThtrdUt`: same on `Thtrd`
* `cAThtr`: `amplitude/amp0` vs `Thtr` → tunes `acr0..acr3`
* `cAThtrd`: same on `Thtrd`

### 4.3 `Rhcorr` / `Rhdcorr` auto-zero ("T-error zero")

Triggered by Form1::Button6 (`DoRhcorr = true`,
[uCal/Unit1.cpp:3515-3518]). On the next `UnpackData` pass
([uCal/Unit1.cpp:1308-1342]) two damped iterations run in parallel
(`Thtr` and `Thtrd`), each up to 1000 steps with gain 0.1, target
absolute error 0.01 °C. The result is stored back as `Rhcorr`/`Rhdcorr`
in `calibration.ini`. This is the in-situ trim that makes the heater R
agree with the chip thermopile at the current operating point —
useful but easily mis-clicked because the result depends on the
*instantaneous* `Ttpl + Taux` reading.

**Done (P1-33):** `Calibration.solve_rhcorr` / `compute_rhcorr` port the exact
damped fixed-point (gain 0.1, tol 0.01 C, <=1000 steps, `|err|>10000`->reset-0)
faithfully. `LocalDeviceController.rhcorr_report` previews the trim at the
current operating point (mean `modes.heater_resistance` and mean `temp` over
powered samples) and `apply_rhcorr` commits it to the *user* calibration file
(never the bundled default); the GUI "R-corr auto-zero" button previews then
writes only on explicit confirmation. PIONER measures only the main heater
resistance (no `Rhtrd` channel), so only `thtrcorr` is auto-zeroed -- the
differential `thtrdcorr` path exists in `Calibration` but has no measured input.

### 4.4 AD595 cold-junction
`Uaux * 100 °C/V` ([uCal/Unit1.cpp:1209]) followed by
`if (Taux < -12) Taux = 2.6843 + 1.2709*T + 0.0042867*T² +
3.4944e-5*T³` ([uCal/Unit1.cpp:1211-1212]). **Bit-for-bit identical**
to the polynomial in `src/pioner/shared/calibration.py:88` and the
default in `HardwareCalibration.ad595_low_correction`.

---

## 5. Acquisition modes

The C++ code has **seven** user-visible modes (vs. three in Python).
Internally they are dispatched off `GenMode` + a small set of
boolean flags (`TRampEnable`, `IRampEnable`, `FreeWriteEnable`,
`fastheating`, `arbWFmode`).

### 5.1 Continuous monitor (`GenMode = 1`, Button7)
`Timer1` (period = `Edit11` ms) calls `transfer_n_display(buffsize)`.
On each AI completion `Timer3` fires `UnpackData` + `CalcAF`, then
sets `Dtr=true` so the timer can loop. No file is written until the
user starts a log (`BitBtn3`/5/7) or a sweep (`Button5`/12/16).
([uCal/Unit1.cpp:2113-2123, 2269-2271])

Random `Sleep(rand()%100)` is injected on every Timer1 tick
([uCal/Unit1.cpp:2120]) — to *desynchronise* repeated acquisitions
from 50/60 Hz mains pickup. **[INFER]** This is a hack; a proper fix
is integer-cycle alignment + filtering.

### 5.2 Sweeps (`GenMode = 2/3/4`)
`Button5`/12/16 → `sweep_af` → `Timer4` → `sweep_f/a/o`. Each sweep
function is a state machine that walks the parameter (`Frequency`,
`Gamp`, or `Goff`) from `Fr1/Am1/Off1` to `Fr2/Am2/Off2` in `Ssteps`
steps. For each step:
1. If parameter changed, call `SineGen(...)` (reconfigure AO0).
2. Wait for AI completion (`Dtr=true`).
3. If overload, bump the appropriate auto-gain TrackBar and retry.
4. Log a `resultdata[i]` and advance.

Phase / amplitude come from `CalcAF`. `RedrawGraph` runs each step;
TXT is auto-saved at the end ([uCal/Unit1.cpp:1696-1704]).

### 5.3 Ramps (continuous log, `GenMode = 1` + flag)
Three close variants share `TempRun` ([uCal/Unit1.cpp:477-606]):

* `FreeWriteEnable` (BitBtn3): just log at whatever temp/voltage you
  set manually.
* `TRampEnable` (BitBtn7): ramp temperature
  `Temperature(t) = StartTemp + TempRate * t`, voltage from
  `TempToVoltage`. Done when `(EndTemp − Temperature) * TempRate ≤ 0`.
* `IRampEnable` (BitBtn5): ramp voltage directly. Same exit test.

A `Beep(); SaveDataTxt(""); SetHeater(StartV)` finishes the ramp; if
the "Hold" checkbox is *not* set, the heater returns to start. Auto-
save every 10 minutes to `!autosave.txt`
([uCal/Unit1.cpp:556-559]).

### 5.4 Fast heating (`fastheating = true`, Button8/BitBtn6/BitBtn10)
This is the analog of the Python `FastHeat` mode and the most
load-bearing path for fast calorimetry.

Two construction routes for the AO waveform:

1. **`BitBtn9Click`** — load a text file of one voltage sample per line
   into `AWbuf`, set `arbWFmode = true`
   ([uCal/Unit1.cpp:3305-3348]).
2. **`BitBtn10Click`** — build `AWbuf` by linear interpolation
   between `(time_ms, target_T)` rows of the `StringGrid`, then
   convert per-sample T→V via `TempToVoltage`
   ([uCal/Unit1.cpp:3350-3395]). Also sets `arbWFmode = true`.

The arming + execution split:

* **`BitBtn6Click`** ([uCal/Unit1.cpp:3277-3303]) calls
  `pulseshoot(u0,n1,u1,n2,u2,counts)` ([uCal/Unit6.cpp:92-170]) which
  arms AO1 with the buffer in NShot mode, **clocked from the ADC
  clock** (the lockstep guarantee).
* The actual triggered AI acquisition then runs through the *separate*
  function **`fastheatrun`** ([uCal/Unit1.cpp:2273-2331]):
  - `VoltGen(2, 4.5)` → enable the hardware switch.
  - `daqAdcSetScan / daqAdcSetAcq(DaamNShot)`,
    `DatsImmediate` start trigger, `DatsScanCount` stop trigger.
  - `daqAdcTransferStart -> daqAdcArm -> daqWaitForEvent(DteAdcDone)`
    blocks until the buffer is full.
  - `VoltGen(2, 0.0)` → release the switch.
  - Computes per-sample T (`Thtr`), per-sample power, and writes
    `resultdata[i]` *at the AI sample rate* (`time = i * 1000/ADclck`,
    in milliseconds).
  - 10-sample warm-up skipped from the result.

**WAIT**: `fastheatrun` arms AI but never re-arms AO1, and AO1 is
*not* armed by the time it runs — that part was done by the prior
`pulseshoot` call. The DAC clock and ADC clock are the same in
`pulseshoot`, so once AI starts (`AdcArm + DatsImmediate`), AO1 fires
in lockstep. **[INFER but probable]** This is the actual mechanism.
The pairing is fragile (separated by user clicks) and worth
re-thinking when porting (see §9).

---

## 6. Lock-in detection (`CalcAF`)

### 6.1 Algorithm ([uCal/Unit1.cpp:721-963])

Inputs: `bufref = ADCdata[0]` (Ihtr / shunt), `bufsig = ADCdata[1]`
(Umod), `buflen`, `fclk = ADclck`, `fgen = Frequency`,
scratch `mult[MULTSIZE]`.

Outputs: globals `ampl` (°C), `phase` (degrees, wrapped to ±180°).

Steps (verified by re-reading):

1. Optional `x2 mode` (Form1->CheckBox1): square the reference,
   effectively detecting the second harmonic
   ([uCal/Unit1.cpp:811-823]).
2. `period = round(fclk/fgen)` samples per cycle. Min 4 samples/period.
3. `nperiods = floor(buflen/fclk*fgen)`, `fullperiods = nperiods*fclk/fgen`
   — integer cycles within the buffer.
4. `xp = clip(floor(1000/period), [1,100])`, `xperiod = round(xp*fclk/fgen)`.
   `xp` is the upsampling factor used to refine phase resolution when
   the natural `fclk/fgen` is small. Phase step is then
   `2π*fgen/fclk/xp` ([uCal/Unit1.cpp:752-756, 760]).
5. Subtract the per-buffer mean from both ref and sig
   ([uCal/Unit1.cpp:805-809]).
6. Normalise the reference so its amplitude is 1: divide by
   `Gamp` (regular) or `Gamp²/2` (x2 mode)
   ([uCal/Unit1.cpp:835-838]).
7. Correlate: for each `i` in `[0, xperiod)` compute
   `mult[i] = mean_j(bufref[j] * bufsig[j + i])` over
   `j ∈ [0, fullperiods - period)` ([uCal/Unit1.cpp:841-868]). When
   `xp > 1` the lookup of `bufsig[i+j]` is linearly interpolated
   on the upsampled grid. This is a brute-force time-domain cross
   correlation.
8. Locate the max → coarse `phase0` and amplitude `(amax-amin)/2`
   ([uCal/Unit1.cpp:874-887]).
9. Rotate `mult[]` so the max is at index `xperiod/2`
   ([uCal/Unit1.cpp:894-895]).
10. Iterate (max 50) on `(phase, ampl, offset)` to minimise the residual
    against a fitted cosine ([uCal/Unit1.cpp:903-934]). Gains:
    1.0 on phase, 0.5 on amplitude, 0.3 on offset.
11. `phase = phase0 + Δphase` then mod 360°, then subtract a
    user-`addphase` ([uCal/Unit1.cpp:944-946]). `addphase` zero-ed by
    Form1::Button9 / Form1::Button13.
12. Final amplitude: `2 * ampl1` (peak units = °C because Umod was
    already converted to °C in `UnpackData` *before* `CalcAF` is
    called from Timer3, [uCal/Unit1.cpp:2795]).

### 6.2 Sanity checks (returned codes)

* `-1` "no lock-in" if `fgen <= 0`.
* `-2` "low sampling rate" if `period < 4`.
* `-3` if `xperiod >= MULTSIZE` (buffer too small / rate too high).
* `-4` if `nperiods < 3` (insufficient acquisition).
* `-5` if `Gamp <= 0`.

### 6.3 Comparison with the Python lock-in

`src/pioner/shared/modulation.py`:

| Trait | Bondar `CalcAF` | Python `lockin_demodulate` | Python `fft_demodulate` |
| --- | --- | --- | --- |
| Domain | time-domain x-corr + iterative fit | sin/cos quadrature + 4th-order Butterworth (sosfiltfilt) | rFFT on integer-cycle slice |
| Output type | scalars `(ampl, phase)` per buffer | per-sample arrays | scalars per requested harmonic |
| Harmonics | x2 mode only, by squaring the ref | n/a | configurable (default 1f/2f/3f) + leakage diagnostic |
| Phase convention | degrees, wrapped ±180° | radians, wrapped ±π | radians, lock-in lag |
| Integer-cycle handling | drops `iskip = period` samples then integrates `fullperiods` | none (LPF smooths) | exact via `_integer_cycle_length` |
| Use of reference channel | yes (bufref = Ihtr) | optional (P1-34): `reference=` AI ch0 re-references the phase; synthetic sin by default | **no** — synthetic only |
| Cost | O(N * xperiod) (often dominates) | O(N log N) Butterworth + O(N) products | O(N log N) once |

**Important physics observation**: the C++ lock-in uses the *measured*
Ihtr as the reference, the Python one uses the *commanded* sinusoid.
For an ideal heater they are equivalent, but at high frequency the
real heater current is shifted in phase relative to the AO command
(LR/RC). Bondar's choice puts the phase reference on the actual
driving force, which is closer to what the AC calorimetry literature
calls the "instrumental phase zero". **Done (P1-34):** `lockin_demodulate`
accepts an optional `reference` (AI ch0) and `reference_phase` extracts its
fundamental lag; the slow/iso time-domain lock-in uses it when the opt-in
`ModulationParams.use_measured_reference` is set. The phase-lag magnitude
still needs bench confirmation before this becomes the default, and the iso
`fft_demodulate` path is not yet covered (see TODO P1-34).

---

## 7. Saved file formats (`SaveDataTxt`, `LoadDataTxt`)

Header line determines schema ([uCal/Unit4.cpp:17-23, 1668-1683]):

| Header | `datatype` | Columns |
| --- | --- | --- |
| `*** data type 1 ***` | 1 | the long row (14 columns) below |
| `*** continuous log ***` | 1 (loaded) | same |
| `*** temperature ramp ***` | 1 (loaded) | same |
| `*** frequency ramp ***` | 2 | long row |
| `*** amplitude ramp ***` | 3 | long row |
| `*** offset ramp ***` | 4 | long row |
| `*** fast heating ***` | 5 | short row: `time(ms) temp temp-fit temp-hr Ref Ihtr Thtr ----- Taux` |

Long row column order:

```
time(s)  amplitude  phase  Ttpl  UhtrG  Ihtr  Thtr  Thtrd
         Taux  frequency  ModAmpl  ModOfset  Resistance  M-power
```

The "fast heating" row uses fields *intentionally repurposed*: in the
`fastheatrun` writeout ([uCal/Unit1.cpp:2310-2320]) the columns are
`time(ms)=resultdata.time`, `temp=ADCdata[2]+Taux`, `temp-fit=`
(unset → 0), `temp-hr=ADCdata[1]+phase`, `Ref=PulseRef[i]`,
`Ihtr=` (omitted!), `Thtr=` polynomial of Rhtr at sample i. So the
"Thtrd" column in fast files is *not* the dynamic R Thtrd of slow
mode — same struct field, different semantics. **Caveat for porting.**

---

## 8. Differences vs. the current Python pipeline

| Topic | Bondar uCal (C++) | Current Python (`src/pioner/`) |
| --- | --- | --- |
| **DAQ vendor** | IOtech (DAQX.DLL, DaqBook 2000 family) | Measurement Computing USB-2627/2637 via `uldaq` |
| **AI channel set** | 5 physical channels {0,1,4,5,3} → logical {Ihtr, Umod, Utpl, Uhtr, Uaux} | identical physical map, see [src/pioner/shared/channels.py:36-41] |
| **Gain on Umod** | hardcoded `/121` in UnpackData | configurable `HardwareCalibration.gain_umod = 121.0` default |
| **Gain on Utpl** | hardcoded `/11` | configurable `gain_utpl = 11.0` default |
| **AD595 polynomial** | identical 4th-order, threshold −12 °C | identical |
| **`heatersafeV` default** | 5.61 V (calibration.ini) | 9.0 V (`Calibration.safe_voltage`) — **looks like a chip/era mismatch worth verifying** |
| **Heater R formula** | `(Uhtr_mV − Ihtr_mV)/Ihtr_mA` — both numerator terms in **mV**, divided by mA → kΩ (off by 1000× vs current code) | `(V_AO − V_shunt + uhtr0) * uhtr1 / ih` in **V/A = Ω** |
| **Lock-in** | time-domain x-correlation + iterative fit, ref = measured Ihtr, x2 mode by squaring | sin/cos + Butterworth (`lockin_demodulate`) or rFFT (`fft_demodulate`) with proper integer-cycle window and explicit harmonics |
| **Phase reference** | measured Ihtr (shunt) | commanded AO sine by default; optional measured AI ch0 via `use_measured_reference` (P1-34, time-domain lock-in) |
| **AO0 vs AO1 split** | AO0 = continuous AC (predefined wave, infinite), AO1 = DC heater or NShot pulse, AO2 = hardware switch | AO1 = single buffer combining DC + AC (via `apply_modulation`), no separate "switch" channel |
| **Slow / iso buffer wrap** | n/a — modes don't replay AO; sweep stops the AO each step | `IsoMode` plays AO buffer indefinitely; `check_ao_period_integrity` verifies seamless wrap |
| **Fast-heat profile build** | `BitBtn10` interpolates StringGrid → AWbuf | JSON program → `_program_to_voltage` → AO buffer |
| **Fast-heat AO/AI sync** | AO1 clocked from AdcClock (`DdcsAdcClock`), AO armed first then AI armed; explicit | both armed via `ExperimentManager.finite_scan` — see [src/pioner/back/experiment_manager.py:153] and todo `P0-5` (AI must be armed before AO) |
| **Modes** | continuous monitor, F-sweep, A-sweep, O-sweep, T-ramp, V-ramp, free-log, fast-heat (7+) | `FastHeat`, `SlowMode`, `IsoMode` (3) |
| **Sweep state machine** | Timer4-driven, blocks in `wait_finish`, auto-gain on overload | absent — `IsoMode` is the closest equivalent (long stationary acquisition) |
| **Storage** | TXT with header line, INI calibration | HDF5 + JSON calibration |
| **Live UI** | scope window with `DoSnapshot`, full mod-amp-offset-rate input, 7-LED `disperror` deviation bar | PyQt main window + plot widgets, no equivalent of `disperror` LED bar |
| **Median + symm-MA post-filter** | `filter_it` with explicit median (Edit1) + smoothing (Edit2) | absent — relies on downstream pandas/scipy |
| **Exp-fit deconvolution** | `removexep`, `fitfallexp`, `fitriseexp` for thermal time-constant removal | absent |
| **AC amplitude correction** | per-T polynomial `kamp(T)`, applied by Form4::BitBtn10 | `Calibration.kamp(Thtr)` divides the amplitude in slow/iso, opt-in via `amplitude_correction_enabled` (P1-32) |
| **Phase zeroing** | `addphase` global, Button9 sets, Button13 resets | absent in `lockin_demodulate` / `fft_demodulate` |
| **Remote control** | Telnet (Unit12, port + login + plaintext password) | Tango / HTTP server (`nanocontrol_tango.py`) |
| **Hardware license** | `CheckS` + `Registr` form | absent |
| **Buffer ceiling** | `MAXBUFFER = 100000` AI samples + `MAXDATABUFF = 100000` records | `MAX_SCAN_SAMPLE_RATE = 1e6`, AI buffer scales with mode |
| **Auto-save** | every 10 min during ramps (`!autosave.txt`) | absent (HDF5 written at run end) |
| **AD/DA settle** | switches between 5 µs and 1 µs at `ADclck > 40 kHz` (bug, see §9.4) | n/a — uldaq settle controlled differently |
| **DAC encoding** | 16-bit unsigned over ±10 V | uldaq native, range configurable |
| **Mock mode** | `runWOhardware` injects synthetic sinusoids inside `UnpackData` ([uCal/Unit1.cpp:1070-1090]) | `mock_uldaq.py` mocks the driver itself |

---

## 9. Potential bugs and points to verify

Each item below is something I noticed while reading. They are not all
"the C++ is wrong" — many are open questions that would have to be
checked against bench measurements or against the chip electronics.
Listed in order of decreasing concern.

### 9.1 Heater R unit confusion in `UnpackData`
Lines [uCal/Unit1.cpp:1276-1279]:
```cpp
if ( Ihtr > 0.001 ) Rhtr = Uhtr / Ihtr;   // mV / mA = ohms
```
Here `Uhtr` is in **mV** (from line 1226 `(Uhtr+uhtro)*uhtrk` where
`Uhtr` was the per-buffer mean in mV from earlier `ADCdata[3] * 1000`),
and `Ihtr` is in **mA** (after `Ihtr*ihtrk + ihtro` on line 1219). So
`Rhtr = mV/mA = Ω` — OK.
But the *dynamic* version on line 1267 uses the same polynomial
(`thtrdk1 + thtrdk2*(Rhtrd+Rhdcorr) + ...`) on `Rhtrd = acurms /
acirms` where both are mV-rms / mA-rms. So unit-consistent here.
The current Python code documents that the legacy formula divided
*both* by 1000 and produced milliohms (see [src/pioner/back/modes.py:250-252]).
**Action**: verify on a bench point that the Python and C++ both
produce R ≈ 1700 Ω for the same chip; if not, the historical
"factor-of-1000" claim needs revisiting against this exact C++
source.

### 9.2 `Uhtr` overwritten by `Uabs`
Lines [uCal/Unit1.cpp:1172-1183]:
```cpp
Uabst += ADCdata[3][i] - ADCdata[0][i]*1000.; // Uhtr_mV - I_shunt_in_mV
...
Uabs = Uabst / icntb;
Uhtr = Uabs;                                  // <-- reassign!
```
So the per-buffer "Uhtr" reported and logged is **not** the raw
heater feedback voltage — it's the IR-drop-corrected estimate. The
calibration ini variable named `Uhtr/k1` (`uhtro`) is then applied to
this *corrected* value. The Python equivalent assumes the same
geometry but does it per-sample (`UHTR_AI - HEATER_CURRENT_AI`,
not on the buffer mean). For low-noise samples this is equivalent;
for very short windows with high modulation amplitude it is **not**.
**Action**: decide whether per-sample (Python) or per-buffer (C++) is
intended for slow/iso modes when reporting `Uhtr` to the user.

### 9.3 `Thtr` IIR averaging hidden in `UnpackData`
Lines [uCal/Unit1.cpp:1389-1392]:
```cpp
Thtr = (Thtr + Thtr1) / 2.;
Thtrd = (Thtrd + Thtrd1) / 2.;
Thtr1 = Thtr; Thtrd1 = Thtrd;
```
A one-sample IIR smoother is applied to the temperature reading before
it gets logged. This introduces a ½-cycle group delay in any "Thtr vs
time" curve — invisible to the user and not documented anywhere. The
Python side has no such hidden smoother. **Action**: if Python users
ever compare "the Thtr value the C++ used to print" against "the
sample-wise Thtr from Python", expect a ~1-cycle lag in legacy logs.

### 9.4 Settle-time switching threshold
Line [uCal/Unit1.cpp:2561]:
```cpp
adclklim = floor(1000000. / chancount / 5.);  // 1e6/5/5 = 40000 Hz
```
Variable named `adclklim` (limit), the comment doesn't exist. The
formula reads "1 MHz / channels / 5" — by analogy with the data sheet
for IOtech DaqBook this is supposed to be the throughput ceiling at
5 µs settle (`5 ch * 5 µs/ch = 25 µs/sample = 40 kHz`). With
`chancount = 5` you get `40 kHz`, so for `ADclck > 40 kHz` settle drops
to 1 µs. **[INFER]** Numerically correct for the IOtech board, may
not match the MCC USB-2627/2637 settling characteristics.

### 9.5 `fastheatrun` + `pulseshoot` separation
`pulseshoot` arms AO1 ([uCal/Unit6.cpp:143-160]) and `fastheatrun`
arms AI ([uCal/Unit1.cpp:2283-2298]). There is no single function that
does both in the correct order; the GUI sequence is implicit
(`BitBtn6Click` triggers `pulseshoot`, then `Button8Click` (with
`fastheating == true`) triggers `fastheatrun`). If the user does
something between the two clicks (re-arms a different DAC mode, opens
another form that calls `daqDacWaveDisarm`, ...) the lockstep is
broken silently. **Action**: in the Python rewrite keep these as a
single atomic call.

### 9.6 X2 mode also zeros `Thtr`
Line [uCal/Unit1.cpp:1289]:
```cpp
if (Form1->CheckBox1->Checked) Thtr = 0.;
```
When the user enables x2 mode (second-harmonic lock-in), the static
`Thtr` from the polynomial is *discarded* — only `Thtrd` is shown.
The TXT export still writes a `Thtr=0` column for those runs, which
will look like a measurement of "Thtr is zero". **Action**: in the
Python port, write NaN (or omit the column) rather than zero.

### 9.7 `addphase` global
Form1::Button9 sets `addphase = phase + addphase`, Form1::Button13
resets to 0 ([uCal/Unit1.cpp:2596-2605]). `CalcAF` subtracts
`addphase` from every reported phase ([uCal/Unit1.cpp:944]). This is
the in-situ phase zeroing the operator does at the start of a session.
**Not stored in calibration.ini** (the value lives only in RAM until
the app closes). So the same chip can have radically different phase
readings between sessions depending on whether the operator clicked
"zero phase". **Action**: the Python pipeline should expose this
control too, *and* persist it as part of the run metadata.

### 9.8 Two `buildpoly` definitions linked
`polleastsq.cpp` and `sqrless.cpp` both define `buildpoly` with the
same signature. The Borland linker would normally complain about
duplicate symbols. The `USEUNIT` list in `NanoCalorimeter.cpp`
includes only `sqrless.cpp` — so **[INFER]** `polleastsq.cpp` is dead
code (or kept compiled-but-unused for historical reasons). Worth
confirming via the build artefacts before assuming `polleastsq`'s
behaviour applies.

### 9.9 Mode-switching is via UI flags, not hardware
`switch2pulse` and `switch2modulation` only change form colours and
toggle `fastheating` ([uCal/Unit1.cpp:3243-3275]). The *actual*
hardware route (continuous sine on AO0 vs. NShot pulse on AO1) is
chosen indirectly:
* `SineGen` arms AO0 in `DdomStaticWave` + `DdwmInfinite`.
* `pulseshoot` arms AO1 in `DdomStaticWave` + `DdwmNShot`.
* The IOtech driver replaces whichever was previously armed when
  `daqDacWaveDisarm` is called.
There is no explicit hardware "switch" beyond the AO2 4.5 V pulse used
in `fastheatrun`. **[INFER]** This means the physical "modulation" vs
"pulse" hardware path is identical — the only thing that changes is
which AO is the active one. Worth confirming when designing the
analog electronics docs.

### 9.10 `samples2per = 400000 / freq`
DAC clock rate computed as `Frequency * samples2per`. For
`freq < 391 Hz`, `samples2per` clips at 1024 → `DAclck = freq * 1024`
(small numbers). For `freq > 100 kHz` the code aborts
([uCal/Unit1.cpp:1509-1520]). For `freq` between ~391 Hz and 100 kHz
the DAC clock is always ~400 kHz, which means the *AO* sample period
is 2.5 µs — matched to the IOtech DAC's typical max rate. **[INFER]**
Hardcoded for the IOtech DaqBook; needs re-evaluation against the
MCC board's DAC ceiling.

### 9.11 Buffer wrap behaviour
The C++ sweeps don't replay AO buffers — every sweep step disarms +
rearms `SineGen`. The Python `IsoMode` plays a single buffer
indefinitely; that's a *new* failure mode (phase discontinuity at
wrap, addressed by `check_ao_period_integrity`). When porting C++ tests
to verify Python, be aware: the C++ behaviour cannot validate the
wrap path because the C++ never wrapped.

### 9.12 `R1htr` "broken/shorted" thresholds
[uCal/Unit1.cpp:1354-1368]: if `R1htr > 9000` the label reads "broken!",
if `< 50` it reads "shorted!", otherwise the numeric value. Hardcoded.
For chips with native resistance far from this 50–9000 Ω window,
the diagnostic is wrong. **Action**: when porting, expose these as
calibration fields.

### 9.13 `Snapshotsignal` is opt-in only
Sets `DoSnapshot=true` via Form3::BitBtn1; consumed once in
`UnpackData -> Snapshotsignal` ([uCal/Unit1.cpp:1394, 2737-2786]).
Writes per-sample `Ref, Umod, Utpl, Uhtr` to
`signal<MMDDhhmmss>.txt`. No per-sample logging by default; for the
Python pipeline this is roughly the equivalent of dumping the raw
DataFrame to HDF5, which we do for every run. **Maybe** keep an
opt-in raw dump in addition to the engineering-unit HDF5 for
debugging.

### 9.14 `Sleep(rand()%100)` jitter
[uCal/Unit1.cpp:2120]. A random jitter on Timer1 ticks. This works as
a poor man's averager against 50/60 Hz mains pickup, but it also
breaks reproducibility — two runs against the same chip will produce
different time series. **Action**: if porting, replace by either
*integer-multiple-of-mains-period* AI windows, or a proper notch
filter, or explicit FFT-based demod with line-frequency rejection.

### 9.15 Buffer-length and AI/AO start ordering
`GetData::Execute` starts the AI by `daqAdcTransferStart` *then*
`daqAdcArm`, with the AO0 running in infinite mode from
`TSineGen::Execute` ([uCal/Unit7.cpp:48-51]). There is **no explicit
synchronisation** between AO and AI other than what `daqAdc*` does
internally. **[INFER]** OK for slow/iso (the AO is steady-state) but
not for fast — which is precisely why fast uses the ADC-clocked AO
path in `pulseshoot`.

### 9.16 Unused / dead-code suspicions
* `OutDigPort` — never called from anywhere I can grep.
* `polleastsq.cpp` — see §9.8.
* `AP.H` — only referenced by `polleastsq.cpp`.
* Form4's `BitBtn10` calibration apply path — duplicated logic across
  `xiT` / `xiTd` branches with copy-pasted code.

---

## 10. What we can lift into the Python pipeline

The C++ is older and crustier in many places, but there are concrete
ideas worth borrowing:

### 10.1 In-situ phase zeroing
Add an "addphase" attribute on the lock-in pipeline that is set by a
GUI button on top of the current `lockin_demodulate` and
`fft_demodulate` outputs (post-processing only). Persist it as part
of the run metadata. See §9.7.

### 10.2 In-situ R-correction ("T-error zero")
The C++ `DoRhcorr` workflow ([uCal/Unit1.cpp:1308-1342]) is a damped
fixed-point iteration that finds the `Rhcorr` value bringing the heater R
into agreement with the thermopile at the current operating point.
**Done (P1-33):** ported as `Calibration.solve_rhcorr`/`compute_rhcorr`
plus `LocalDeviceController.rhcorr_report`/`apply_rhcorr` and a GUI button;
see §4.3 for the full description.

### 10.3 AC amplitude correction `acr0..acr3`
The fields are *already* in `Calibration`. **Done (P1-32):**
`Calibration.kamp(T) = ac0 + ac1*T + ac2*T^2 + ac3*T^3` and
`back.modes._kamp_divide` divide the demodulated amplitude by `kamp(Thtr)`
in the slow/iso post-processing (per-sample trace + iso FFT scalars). It is
opt-in via `amplitude_correction_enabled` (off by default): the bundled
identity calibration uses the placeholder `ac={0,1,0,0}` which gives
`kamp(T)=T` (not 1), so applying it unconditionally would divide the
amplitude by the temperature. `Thtr` is used as `T` (Bondar fits `acr`
against `Thtr`, cAThtr); samples where `kamp<=0` or `Thtr` is NaN are
marked NaN rather than silently mis-divided.

### 10.4 X2-mode / harmonic detection
The C++ ad-hoc x2 mode (square the reference) is inferior to the
Python `fft_demodulate(harmonics=(1,2,3))` *if the modulation is
clean*. Keep the FFT path as the default and consider deprecating the
x2 toggle entirely.

### 10.5 Telnet/CLI-style remote field setters
The `FI<XXXX>...` protocol in Unit12 is a low-bandwidth way to
control the rig over a terminal session. Equivalent surface in
Tango/HTTP would be the per-attribute setters — already present. No
porting needed, just confirm the same field set is reachable.

### 10.6 Median + symmetric MA filter pair
`Form4::filter_it` applies `median(strength=Edit1)` then
`intfilter(strength=Edit2)` to amplitude/phase/Ttpl/Thtr arrays. This
is a useful operator-controlled post-filter pair. Easy to add as a
helper on the result DataFrame.

### 10.7 Exp-fit deconvolution
`removexep` ([uCal/Unit4.cpp:3085-3121]) splits the data into rising
and falling halves (around the midpoint Uhtr crossing) and fits a
single exponential to each, subtracting them — this is a poor man's
thermal-time-constant removal. For a fast-heat run the residual is
the small calorimetric signal of interest. Worth offering as a
post-processing helper.

### 10.8 Per-sample AD595 trace
The C++ already averages AD595 over the whole scan
([uCal/Unit1.cpp:1209]). The current Python TODO at
[src/pioner/back/modes.py:205-208] flags this as a known limitation
("for slow ramps >30 s the cold-junction can drift by O(0.5 °C)").
The Bondar code has the same flaw — no fix to borrow, but the
finding above confirms the problem is real.

### 10.9 IR-drop-corrected `Uhtr` for display
The C++ replaces displayed `Uhtr` with `Uabs = Uhtr_raw - I*R_shunt_V`
([uCal/Unit1.cpp:1172-1183]). The Python pipeline keeps both
quantities separate (`Uref` = AO command, plus the raw AI channels).
Consider exposing a derived `Uhtr_eff` = `UHTR_AI - HEATER_CURRENT_AI`
column in the engineering-unit DataFrame for parity.

### 10.10 7-LED deviation bar (`disperror`)
A visual at-a-glance "how mis-calibrated is the chip right now?"
indicator. The bar lights up at ±1/2/3/5 °C ([uCal/Unit1.cpp:2929-3021]).
Cheap to replicate in PyQt — a strip of QLabel widgets driven by
`Thtr − (Ttpl + Taux)` deviation from the current sample.

### 10.11 Auto-save during long ramps
The C++ writes `!autosave.txt` every 10 minutes during a ramp
([uCal/Unit1.cpp:556-559]). The Python pipeline saves at the *end* of
a run. For long iso runs (hours) the C++ behaviour is the safer
default; a periodic flush to an "in-progress" HDF5 group would
mirror it.

### 10.12 `Kadapt` parameter
A user-settable gain for the fast-heat profile, persisted in
`setup.ini` ([uCal/Unit1.cpp:230, 297, 103]). Not used inside the
files I read end-to-end, but the variable exists — **[INFER]** it
probably scales the AWbuf before output to compensate for an adaptive
P-loop. Worth grepping the closer-to-hardware paths if we choose to
port the fast-heat profile editor wholesale.

### 10.13 Settle-time auto-switch
Replicating the `>40 kHz → 1 µs settle` rule on the MCC board needs a
data-sheet check; uldaq has an equivalent `SettleTime` knob.
**Action**: confirm and expose as a settings field rather than a
hardcoded constant.

---

## 11. Glossary cheat-sheet for the C++ -> Python port

| C++ identifier | Python equivalent | Notes |
| --- | --- | --- |
| `ADclck` | `ai_sample_rate` | AI sample clock in Hz |
| `DAclck` | `ao_sample_rate` | AO sample clock in Hz |
| `buffsize` | `samples_per_channel` | AI buffer length |
| `Frequency`, `Gamp`, `Goff` | `ModulationParams(frequency, amplitude, offset)` | |
| `Fr1/Fr2/Am1/Am2/Off1/Off2/Ssteps` | sweep parameters (no direct equivalent) | |
| `Uref` | AI ch 0 (`HEATER_CURRENT_AI`) | the shunt voltage as the lock-in reference |
| `Umod` | AI ch 1 (`UMOD_AI`) | |
| `Utpl` | AI ch 4 (`UTPL_AI`) | |
| `Uhtr` (struct field) | derived "Uhtr" = `UHTR_AI - HEATER_CURRENT_AI` | C++ replaces raw with IR-corrected on the fly |
| `Uabs` (local) | same IR-corrected V as above | |
| `Ihtr` (struct field) | `ihtr0 + ihtr1 * V_shunt` (`HEATER_CURRENT_AI` channel) | C++ produces mA, Python A |
| `Thtr` (struct field) | `Thtr` column in engineering-unit DataFrame | |
| `Thtrd` (struct field) | n/a — Python doesn't compute "dynamic R" separately | the C++ does both static and dynamic |
| `Ttpl` (struct field) | `temp` column from `apply_calibration` | |
| `Taux` (struct field) | `Taux` column from `apply_calibration` | AD595 cold-junction |
| `R1htr` (struct field) | `Uhtr_eff / Ihtr` if you choose to compute it | |
| `power` (struct field) | n/a directly — derived per-buffer | C++ uses peak-power formula on `(Goff ± Gamp)` |
| `addphase` (global) | n/a | user-defined phase zero |
| `Rhcorr` / `Rhdcorr` | `Calibration.thtrcorr` / `thtrdcorr` | in-situ R adjustments |
| `acr0..acr3` | `Calibration.ac0..ac3` | AC amplitude correction; not yet applied in Python |
| `itk2/k3/k4` | `Calibration.theater0/1/2` | V→T_chip cubic |
| `ttplo`, `ttplk`, `ttplk2` | `Calibration.utpl0`, `ttpl0`, `ttpl1` | thermopile V→T |
| `thtrk1..k3` | `Calibration.thtr0..2` | R→T_heater |
| `thtrdk1..k3` | `Calibration.thtrd0..2` | R→T_heater dynamic |
| `uhtro`, `uhtrk` | `Calibration.uhtr0`, `uhtr1` | |
| `ihtro`, `ihtrk` | `Calibration.ihtr0`, `ihtr1` | |
| `heatersafeV` | `Calibration.safe_voltage` | clamp ceiling |
| `MAXCHANCOUNT` | `len(DEFAULT_AI_CHANNELS) == 5` | |
| `MAXBUFFER` | `MAX_SCAN_SAMPLE_RATE` (different semantic — rate vs length) | |

---

**Versioning notes:**
* This document was written against `uCal/` (the 1.3.0.1 branch with
  Telnet remote control). Items marked `[INFER]` were not directly
  verified against bench tests on real hardware.
* Cross-referenced against Python sources as of the current `main`
  branch (`src/pioner/back/modes.py`, `src/pioner/shared/{calibration,
  channels, constants, modulation}.py`).
* All line numbers refer to the *current* files in
  `Bondar-uCal/uCal/`; the `uCal_/` snapshot is older and slightly
  smaller (no Unit12). Major code paths in `Unit1.cpp` / `Unit4.cpp`
  are nearly identical between the two snapshots.
