"""Three calorimetry experiment modes built on top of :class:`ExperimentManager`.

The modes share the following pipeline:

1. *Validate* the time/temperature program supplied by the user.
2. *Build* the AO voltage profile (per channel) by interpolating the program
   onto the AO sample grid and converting from temperature to voltage via the
   chip calibration where requested. For ``slow`` and ``iso``, an AC
   modulation is added on the heater channel.
3. *Arm* the experiment manager: the AO buffer is pushed to the DAQ board
   but not started yet.
4. *Run* the experiment: AO and AI are started together, AI is collected
   without any sample loss, and the resulting raw frame is post-processed
   into engineering units (Taux, Thtr, T, Uref, ...).
5. *Demodulate* (slow / iso only): a software lock-in extracts the AC
   amplitude and phase of the temperature response at the modulation
   frequency, which is what nanocalorimetry actually cares about.

Each concrete mode (``FastHeat``, ``SlowMode``, ``IsoMode``) is a thin
specialisation of the same pipeline. The Tango server picks one based on a
string identifier.

All time arrays are expressed in **milliseconds** (matching the GUI). All
voltages in **volts**.
"""

from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, cast

import numpy as np
import pandas as pd

from pioner.shared.calibration import Calibration
from pioner.shared.channels import (
    AD595_AI,
    DEFAULT_AI_CHANNELS,
    HEATER_AO,
    HEATER_CURRENT_AI,
    UHTR_AI,
    UMOD_AI,
    UTPL_AI,
    channel_index,
    channel_key,
)
from pioner.shared.modulation import (
    AOPeriodReport,
    ModulationParams,
    apply_modulation,
    check_ao_period_integrity,
    fft_demodulate,
    lockin_demodulate,
)
from pioner.shared.settings import BackSettings, ExperimentLimits
from pioner.shared.utils import temperature_to_voltage
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.experiment_manager import ExperimentManager, ScanResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Program validation and AO profile generation
# ---------------------------------------------------------------------------
@dataclass
class ChannelProgram:
    """A single AO channel program in the user-facing ``time/temp_or_volt`` form."""

    time_ms: np.ndarray         # monotone, starts at 0, ends at total duration
    values: np.ndarray          # same length as ``time_ms``
    is_temperature: bool        # ``True`` => values in °C (calibration applied)


def _to_channel_program(table: dict) -> ChannelProgram:
    if "time" not in table:
        raise ValueError(f"channel program missing 'time' key: {table}")
    keys = [k for k in table if k != "time"]
    if len(keys) != 1 or keys[0] not in ("temp", "volt"):
        raise ValueError(
            f"channel program must contain exactly one of 'temp' or 'volt'; got {keys}"
        )
    is_temp = keys[0] == "temp"
    time_ms = np.asarray(table["time"], dtype=float)
    values = np.asarray(table[keys[0]], dtype=float)
    if time_ms.ndim != 1 or values.ndim != 1:
        raise ValueError("'time' and the value array must be 1-D")
    if time_ms.size != values.size:
        raise ValueError(
            f"'time' ({time_ms.size}) and value ({values.size}) arrays must have "
            "the same length"
        )
    if time_ms.size < 2:
        raise ValueError("a channel program must have at least 2 points")
    if not np.all(np.diff(time_ms) >= 0):
        raise ValueError("'time' must be non-decreasing")
    if time_ms[0] != 0.0:
        raise ValueError("'time' must start at 0 ms")
    return ChannelProgram(time_ms=time_ms, values=values, is_temperature=is_temp)


def _validate_programs(
    programs: Dict[str, ChannelProgram],
    ao_low: int,
    ao_high: int,
) -> float:
    """Return the common duration in ms after validating channel keys/durations."""
    if not programs:
        raise ValueError("at least one channel program is required")
    durations = {p.time_ms[-1] for p in programs.values()}
    if len(durations) > 1:
        raise ValueError(f"channel programs have inconsistent durations: {durations}")
    total_ms = durations.pop()
    if total_ms <= 0:
        raise ValueError("program duration must be > 0 ms")
    # Fractional-second durations are allowed: the AI buffer stays one second
    # and ``ExperimentManager._collect_finite_ai`` collects whole half-buffer
    # chunks, then trims to the exact ``total_samples_per_channel`` (which is
    # ``round(sample_rate * total_s)``). The kept samples are the leading,
    # AO-aligned ones, so a non-integer second is just a shorter trim.
    valid_keys = {channel_key(i) for i in range(ao_low, ao_high + 1)}
    bad_keys = set(programs) - valid_keys
    if bad_keys:
        raise ValueError(
            f"AO channel keys outside [{ao_low}, {ao_high}]: {sorted(bad_keys)}"
        )
    return float(total_ms)


def _validate_program_limits(
    programs: Dict[str, ChannelProgram], limits: ExperimentLimits
) -> None:
    """Fail-loud safety check of **temperature** programs (step 8 / P1-38).

    Rejects temperature points outside the heating-only allowed range
    ``[min_temp, max_temp]`` (no cryostat) and, when the rate bounds are set,
    per-segment ramp rates that fall outside ``[min_heat_rate, max_heat_rate]``
    (heating) or ``[min_cool_rate, max_cool_rate]`` (cooling, magnitude; a cool
    segment faster than the chip's passive relaxation can't be followed).
    Voltage programs are skipped (raw V, not temperature). A no-op when limits
    are the defaults and no temp program is out of range.
    """
    for ch, prog in programs.items():
        if not prog.is_temperature or prog.values.size == 0:
            continue
        lo = float(np.min(prog.values))
        hi = float(np.max(prog.values))
        if lo < limits.min_temp - 1e-9 or hi > limits.max_temp + 1e-9:
            raise ValueError(
                f"channel {ch} temperature range [{lo:.1f}, {hi:.1f}] C is outside "
                f"the allowed [{limits.min_temp:.1f}, {limits.max_temp:.1f}] C "
                "(heating-only; no cryostat)"
            )
        if (limits.min_heat_rate is None and limits.max_heat_rate is None
                and limits.min_cool_rate is None and limits.max_cool_rate is None):
            continue
        t, temp = prog.time_ms, prog.values
        for i in range(len(t) - 1):
            dt_s = (t[i + 1] - t[i]) / 1000.0
            if dt_s <= 0:
                continue
            rate = (temp[i + 1] - temp[i]) / dt_s   # K/s, signed
            if rate > 0:
                if (limits.max_heat_rate is not None
                        and rate > limits.max_heat_rate + 1e-9):
                    raise ValueError(
                        f"channel {ch} segment {i}: heat rate {rate:.3g} K/s exceeds "
                        f"max {limits.max_heat_rate:.3g} K/s"
                    )
                if (limits.min_heat_rate is not None
                        and rate < limits.min_heat_rate - 1e-9):
                    raise ValueError(
                        f"channel {ch} segment {i}: heat rate {rate:.3g} K/s is below "
                        f"min {limits.min_heat_rate:.3g} K/s"
                    )
            if rate < 0:
                if (limits.max_cool_rate is not None
                        and -rate > limits.max_cool_rate + 1e-9):
                    raise ValueError(
                        f"channel {ch} segment {i}: cool rate {-rate:.3g} K/s exceeds "
                        f"max passive {limits.max_cool_rate:.3g} K/s (no cryostat)"
                    )
                if (limits.min_cool_rate is not None
                        and -rate < limits.min_cool_rate - 1e-9):
                    raise ValueError(
                        f"channel {ch} segment {i}: cool rate {-rate:.3g} K/s is below "
                        f"min {limits.min_cool_rate:.3g} K/s"
                    )


def segments_to_program(
    segments: Sequence[dict], start_temp: float = 0.0
) -> Dict[str, list]:
    """Compile heat / iso / cool segments into a ``(time, temp)`` program (P1-39).

    The core of the multi-segment builder: a friendlier description than raw
    points. Each segment is ``{"type": "heat"|"iso"|"cool", "duration_ms": D,
    "target": T}`` (``target`` ignored for ``iso``, which holds the current
    temperature). Returns ``{"time": [ms...], "temp": [degC...]}`` ready to drop
    into a channel program (e.g. ``{"ch1": segments_to_program(...)}``); the
    usual `_validate_programs` / `_validate_program_limits` then guard it.

    ``heat`` must not target below the current temperature and ``cool`` must not
    target above it (heating-only; cooling is passive).
    """
    times: list = [0.0]
    temps: list = [float(start_temp)]
    cur = float(start_temp)
    for i, seg in enumerate(segments):
        typ = seg.get("type")
        duration = float(seg.get("duration_ms", 0.0))
        if duration <= 0:
            raise ValueError(f"segment {i}: duration_ms must be > 0")
        if typ == "iso":
            target = cur
        elif typ == "heat":
            target = float(seg["target"])
            if target < cur:
                raise ValueError(
                    f"segment {i}: heat target {target} C is below the current {cur} C"
                )
        elif typ == "cool":
            target = float(seg["target"])
            if target > cur:
                raise ValueError(
                    f"segment {i}: cool target {target} C is above the current {cur} C"
                )
        else:
            raise ValueError(f"segment {i}: unknown type {typ!r} (heat|iso|cool)")
        times.append(times[-1] + duration)
        temps.append(target)
        cur = target
    return {"time": times, "temp": temps}


def _interpolate_program(
    program: ChannelProgram,
    samples_per_channel: int,
) -> np.ndarray:
    """Linearly interpolate a user program onto the AO sample grid (V or °C)."""
    grid = np.linspace(program.time_ms[0], program.time_ms[-1], samples_per_channel)
    return np.interp(grid, program.time_ms, program.values)


def _program_to_voltage(
    program: ChannelProgram,
    samples_per_channel: int,
    calibration: Calibration,
) -> np.ndarray:
    """Interpolate and, if needed, convert temperature -> voltage.

    For temperature programs, :func:`temperature_to_voltage` already clamps
    the result into ``[0, safe_voltage]``. For raw ``volt`` programs we do
    *not* auto-clip (the user may legitimately want negative voltages, e.g.
    on a guard channel), but we log a warning if the requested peak exceeds
    ``safe_voltage`` so the operator notices before the chip is damaged.
    """
    arr = _interpolate_program(program, samples_per_channel)
    if program.is_temperature:
        arr = temperature_to_voltage(arr, calibration)
    elif arr.size:
        peak = float(np.nanmax(np.abs(arr)))
        if peak > calibration.safe_voltage:
            logger.warning(
                "Voltage program peak |V|=%.3f V exceeds safe_voltage=%.3f V; "
                "the heater may saturate or be damaged.",
                peak,
                calibration.safe_voltage,
            )
    return arr


def _clip_modulation_to_safe(
    arr: np.ndarray, safe_voltage: float, channel: str
) -> None:
    """Clip ``arr`` to ``[0, safe_voltage]`` in place, warning if anything was
    actually clipped.

    A silent clip turns the AC drive into a trapezoid (the sine peaks are flat-
    topped) and biases the recovered lock-in amplitude with no trace in the
    logs -- e.g. ``DC=8.5 V, A=2 V, safe=9 V`` clips half of every period. Warn
    so the operator can drop the DC offset or amplitude (P1-4).
    """
    if arr.size == 0:
        return
    lo, hi = float(arr.min()), float(arr.max())
    if lo < 0.0 or hi > safe_voltage:
        n_clipped = int(np.count_nonzero((arr < 0.0) | (arr > safe_voltage)))
        logger.warning(
            "Modulation on %s clipped to [0, %.3f] V: %d/%d samples out of "
            "range (min=%.3f V, max=%.3f V). The AC drive is distorted and the "
            "lock-in amplitude will be biased; reduce the DC offset or amplitude.",
            channel, safe_voltage, n_clipped, arr.size, lo, hi,
        )
    np.clip(arr, 0.0, safe_voltage, out=arr)


# ---------------------------------------------------------------------------
# Calibration application: raw AI counts -> engineering units
# ---------------------------------------------------------------------------
def apply_calibration(
    raw: pd.DataFrame,
    sample_rate: float,
    calibration: Calibration,
    voltage_profiles: Dict[str, np.ndarray],
    ai_channels: Sequence[int] = DEFAULT_AI_CHANNELS,
    taux_override: Optional[float] = None,
    sample_offset: int = 0,
) -> pd.DataFrame:
    """Convert raw AI samples into engineering units (Taux, Thtr, T, ...).

    The historical implementation lived in ``FastHeat._apply_calibration`` with
    several magic constants hard-coded. The amplifier gains and AD595
    correction polynomial are now read from
    :attr:`Calibration.hardware`.

    ``taux_override`` / ``sample_offset`` make this safe to call **per block** on
    a slice of a larger scan (chunked finalise, P1-17 step 4c-1). ``Taux`` is the
    only whole-scan quantity (AD595 mean); pass the globally-computed value as
    ``taux_override`` so every block agrees. ``sample_offset`` is the block's
    first-sample index so the ``time`` column is continuous across blocks. The
    defaults reproduce the original whole-frame behaviour exactly.
    """
    df = raw.copy()
    if df.empty:
        return df

    # Time scale in ms (offset by the block's first-sample index).
    df["time"] = ((sample_offset + np.arange(len(df))) * 1000.0) / sample_rate

    hw = calibration.hardware

    # AD595 cold-junction temperature (channel 3, scaled 100 °C/V then
    # corrected below -12 °C).
    # TODO(physical): we currently average the AD595 trace over the whole scan
    # which loses any drift information. For long slow ramps (>30 s) the
    # cold-junction can drift by O(0.5 °C). Replace ``mean()`` by either a
    # per-sample correction or a low-pass-filtered trace.
    # TODO(diagnostic): expose an FFT spectrum of AI ch3 (AD595) as part of
    # the apply_calibration diagnostics so 50/60 Hz mains pickup on the cold
    # junction is visible quantitatively. Cheap to add (one np.fft.rfft per
    # scan); see ``shared.modulation.fft_demodulate`` for the pattern.
    if taux_override is not None:
        # Block-wise finalise: the caller computed the whole-scan AD595 mean in
        # a streaming first pass and passes it here so every block agrees.
        df["Taux"] = taux_override
    elif AD595_AI in df.columns:
        u_aux = float(cast(pd.Series, df[AD595_AI]).mean())
        t_aux = 100.0 * u_aux
        t_aux = hw.correct_ad595(t_aux)
        df["Taux"] = t_aux
    else:
        df["Taux"] = 0.0

    # Thermopile temperature on the standard channel (Utpl) and on the
    # high-resolution modulation channel (Umod).
    # Work from local variables rather than overwriting the raw ``df[N]``
    # columns in place: the raw integer-named columns stay untouched until the
    # final ``df.drop``, so this block is no longer order-sensitive (a reorder
    # cannot silently feed an already-scaled column back into another step).
    if UTPL_AI in df.columns:
        u_tpl_mv = df[UTPL_AI] * (1000.0 / hw.gain_utpl)  # mV at front-end
        ax = u_tpl_mv + calibration.utpl0
        df["temp"] = (
            calibration.ttpl0 * ax + calibration.ttpl1 * (ax**2)
        )
        df["temp"] += df["Taux"]
    if UMOD_AI in df.columns:
        u_mod_mv = df[UMOD_AI] * (1000.0 / hw.gain_umod)
        ax_hr = u_mod_mv + calibration.utpl0
        df["temp-hr"] = (
            calibration.ttpl0 * ax_hr + calibration.ttpl1 * (ax_hr**2)
        )

    # Heater temperature derived from V_heater / ih.
    #
    # AI ch0 (HEATER_CURRENT_AI): node between the series resistor and the
    # amplifier loop -- a voltage proxy for heater current. It is NOT a shunt
    # voltage with a known R_shunt. Production calibration uses ihtr0=0,
    # ihtr1=1, so ih = V_ch0 in volts (not amperes). The Thtr polynomial is
    # fitted against this proxy directly, so Rhtr = V_heater / ih is
    # dimensionless (V/V) and the polynomial coefficients absorb the
    # implicit scaling (todo P2-21 tracks proper SI calibration).
    #
    # AI ch5 (UHTR_AI): inverted heater drive signal after the amplifier --
    # proportional to the voltage applied to the heater, without gain.
    # V_heater_proxy = (AI5 - AI0 + uhtr0) * uhtr1.
    #
    # The Thtr polynomial (thtr0=-1069.7, thtr1=0.78336, thtr2=-8.67e-5)
    # was fitted against proxy Rhtr (V/V), NOT physical ohms.
    # At idle (ih ~ 0) Rhtr is undefined; mark NaN (see nz guard below).
    if UHTR_AI in df.columns and HEATER_CURRENT_AI in df.columns:
        ih = cast(
            pd.Series,
            calibration.ihtr0 + df[HEATER_CURRENT_AI] * calibration.ihtr1,
        )
        # When the heater is idle (current ~ 0) R_heater is undefined. The
        # historical implementation used 0 as a sentinel which then evaluated
        # to ``thtr0 + thtr1*thtrcorr + ...`` and produced a physically
        # meaningless number (~ -1070 C with the production polynomial).
        # Mark those samples as NaN so downstream code / plots can skip them.
        nz = ih.abs() > 1e-9
        rhtr = pd.Series(np.full(len(df), np.nan), index=df.index)
        rhtr.loc[nz] = (
            (df.loc[nz, UHTR_AI] - df.loc[nz, HEATER_CURRENT_AI]
             + calibration.uhtr0)
            * calibration.uhtr1
            / ih.loc[nz]
        )
        thtr = (
            calibration.thtr0
            + calibration.thtr1 * (rhtr + calibration.thtrcorr)
            + calibration.thtr2 * ((rhtr + calibration.thtrcorr) ** 2)
        )
        df["Thtr"] = thtr

    # Provide the heater AO trace for context.
    if HEATER_AO in voltage_profiles:
        ref = np.asarray(voltage_profiles[HEATER_AO], dtype=float)
        if ref.size == 0:
            df["Uref"] = np.full(len(df), np.nan)
        elif ref.size >= len(df):
            df["Uref"] = ref[: len(df)]
        else:
            # Iso/CONTINUOUS AO replays the same buffer indefinitely (and a
            # DC iso profile is just a single sample). Tile the commanded
            # voltage to match the AI length so Uref reflects what the AO
            # was actually putting out at every AI sample, not just the
            # first second.
            repeats = int(np.ceil(len(df) / ref.size))
            df["Uref"] = np.tile(ref, repeats)[: len(df)]

    # Drop the raw integer-named columns; the engineering-unit columns are the
    # public output.
    df = df.drop(columns=[c for c in ai_channels if c in df.columns])
    return df


# ---------------------------------------------------------------------------
# Base mode and concrete implementations
# ---------------------------------------------------------------------------
class BaseMode(abc.ABC):
    """Common skeleton for all calorimetry modes."""

    name: str = "base"

    def __init__(
        self,
        daq: DaqDeviceHandler,
        settings: BackSettings,
        calibration: Calibration,
        programs: Dict[str, dict],
        ai_channels: Sequence[int] = DEFAULT_AI_CHANNELS,
    ) -> None:
        self._daq = daq
        self._settings = settings
        self._calibration = calibration
        self._ai_channels = list(ai_channels)
        self._programs: Dict[str, ChannelProgram] = {
            ch: _to_channel_program(table) for ch, table in programs.items()
        }
        self._duration_ms: Optional[float] = None
        self._voltage_profiles: Dict[str, np.ndarray] = {}
        self._samples_per_channel: int = 0
        # ExperimentManager of an in-flight run(), exposed so stop() can abort
        # it from another thread (P1-17 step 3). None when no run is active.
        self._active_em: Optional[ExperimentManager] = None

    # ------------------------------------------------------------------
    # Arming / introspection
    # ------------------------------------------------------------------
    def arm(self) -> None:
        """Validate inputs and build the AO voltage profiles."""
        ao = self._settings.ao_params
        self._duration_ms = _validate_programs(
            self._programs, ao.low_channel, ao.high_channel
        )
        # Operator safety limits (heating-only temperature range + per-segment
        # ramp rates) -- fail loud before building the profile (step 8 / P1-38).
        # Prefer this mode's per-mode limit set (fast/slow/iso differ); fall back
        # to the scalar ``limits`` for an unknown mode or a legacy settings object.
        limits_by_mode = getattr(self._settings, "limits_by_mode", None)
        if limits_by_mode is not None and self.name in limits_by_mode:
            limits = limits_by_mode[self.name]
        else:
            limits = getattr(self._settings, "limits", None)
        if limits is not None:
            _validate_program_limits(self._programs, limits)
        seconds = self._duration_ms / 1000.0
        self._samples_per_channel = int(round(ao.sample_rate * seconds))
        self._voltage_profiles = self._build_profiles()
        self._post_arm_check()

    def is_armed(self) -> bool:
        return bool(self._voltage_profiles)

    @property
    def voltage_profiles(self) -> Dict[str, np.ndarray]:
        return self._voltage_profiles

    @property
    def duration_seconds(self) -> float:
        if self._duration_ms is None:
            raise RuntimeError("Mode is not armed yet")
        return self._duration_ms / 1000.0

    # ------------------------------------------------------------------
    # Voltage profile assembly (overridable by concrete modes)
    # ------------------------------------------------------------------
    def _build_profiles(self) -> Dict[str, np.ndarray]:
        return {
            ch: _program_to_voltage(
                program, self._samples_per_channel, self._calibration
            )
            for ch, program in self._programs.items()
        }

    def _post_arm_check(self) -> None:
        """Hook for concrete modes; default is a no-op."""

    def stop(self) -> None:
        """Cooperatively abort an in-flight run() from another thread (P1-17).

        No-op if nothing is running. The active ExperimentManager's collect
        loop polls the cancel flag, stops the scan, and zeroes AO on abort.
        IsoMode overrides this with its own ring-stop event.
        """
        em = self._active_em
        if em is not None:
            em.request_stop()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def run(self) -> pd.DataFrame:
        ...


class FastHeat(BaseMode):
    """Ballistic heating up to >1000 K/s. Always single-shot, no modulation."""

    name = "fast"

    def run(self) -> pd.DataFrame:
        if not self.is_armed():
            raise RuntimeError("FastHeat is not armed; call arm() first")

        with ExperimentManager(self._daq, self._settings) as em:
            # Fast-heat uses the single-shot DEFAULTIO full-buffer scan: the
            # host reads once at the end, so the ballistic high-rate scan cannot
            # hit a FIFO OVERRUN (todo P1-30). Slow keeps the CONTINUOUS path.
            self._active_em = em  # expose for stop() while the scan runs
            try:
                result = em.finite_scan(
                    self._voltage_profiles,
                    self._ai_channels,
                    seconds=self.duration_seconds,
                    single_shot=True,
                )
            finally:
                self._active_em = None
        return apply_calibration(
            result.data,
            sample_rate=result.ai_rate,
            calibration=self._calibration,
            voltage_profiles=self._voltage_profiles,
            ai_channels=self._ai_channels,
        )


class SlowMode(BaseMode):
    """Slow ramp + AC modulation on the heater channel.

    AC parameters come from the BackSettings ``modulation`` block. The default
    heater channel for modulation is ``ch1`` (the same channel the GUI uses
    for the temperature program); pass ``modulation_channel`` to override.
    """

    name = "slow"

    def __init__(
        self,
        *args,
        modulation: Optional[ModulationParams] = None,
        modulation_channel: str = HEATER_AO,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._modulation = modulation
        self._modulation_channel = modulation_channel
        # Abort flag for the injected (off-ring) path, which waits on it instead
        # of running a finite scan. The owned finite_scan path is aborted via
        # BaseMode.stop() -> ExperimentManager.request_stop().
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Abort an in-flight run from another thread (owned or injected)."""
        self._stop_event.set()
        super().stop()  # request_stop on the owned finite_scan, if any

    def _build_profiles(self) -> Dict[str, np.ndarray]:
        profiles = super()._build_profiles()
        params = self._modulation or self._settings.modulation
        if not params.enabled:
            return profiles
        if self._modulation_channel not in profiles:
            raise ValueError(
                f"modulation channel {self._modulation_channel!r} not in programs"
            )
        rate = self._settings.ao_params.sample_rate
        time_s = np.arange(self._samples_per_channel) / float(rate)
        profiles[self._modulation_channel] = apply_modulation(
            time_s, profiles[self._modulation_channel], params
        )
        # Clamp to the safe voltage envelope so we cannot saturate the heater
        # (warns if the modulation actually had to be clipped -- P1-4).
        _clip_modulation_to_safe(
            profiles[self._modulation_channel],
            self._calibration.safe_voltage,
            self._modulation_channel,
        )
        return profiles

    def run(
        self,
        em: Optional[ExperimentManager] = None,
        snapshot: Optional[Callable[[], np.ndarray]] = None,
    ) -> pd.DataFrame:
        """Run the slow ramp and return a calibrated DataFrame.

        Two paths (mirroring :class:`IsoMode`):

        * **Owned** (``em is None``, default / Tango / scripts): create a private
          :class:`ExperimentManager` and run a finite AO+AI scan (CONTINUOUS AI
          half-flip). Self-contained but the AI scan collides with a persistent
          ring, so a caller streaming live must pause it.
        * **Injected** (``em`` + ``snapshot`` supplied, P1-17 step 4b "off-ring"):
          drive **only** the ramp AO on the caller's manager and read AI from
          the caller's already-running persistent ring via ``snapshot`` -- no
          second AI scan, so the live stream is never paused. Stops only AO.
        """
        if not self.is_armed():
            raise RuntimeError("SlowMode is not armed; call arm() first")
        if em is not None:
            return self._run_injected(em, snapshot)
        return self._run_owned()

    def _run_owned(self) -> pd.DataFrame:
        with ExperimentManager(self._daq, self._settings) as em:
            self._active_em = em  # expose for stop() while the scan runs
            try:
                result = em.finite_scan(
                    self._voltage_profiles,
                    self._ai_channels,
                    seconds=self.duration_seconds,
                )
            finally:
                self._active_em = None
        return self._finish(result.data, result.ai_rate)

    def _run_injected(
        self, em: ExperimentManager, snapshot: Optional[Callable[[], np.ndarray]]
    ) -> pd.DataFrame:
        self._stop_event.clear()
        rate = self._settings.ai_params.sample_rate
        total = int(round(rate * self.duration_seconds))
        try:
            # Drive the ramp (with AC if enabled) on the caller's manager. The
            # CONTINUOUS buffer is the full ramp; we hold it for the ramp
            # duration (or until stop()) and never let it loop.
            em.stop_ao()
            em.ao_modulated(self._voltage_profiles)
            self._stop_event.wait(timeout=self.duration_seconds)
            samples = snapshot() if snapshot is not None else np.empty((0, 0), dtype=float)
        finally:
            em.stop_ao()  # drop only AO; the caller's AI ring keeps running

        if samples.size == 0:
            return pd.DataFrame(columns=["time", "Taux", "Thtr", "temp", "temp-hr"])
        # Trim to the ramp length so apply_calibration aligns Uref to the
        # commanded ramp (extra samples would hit the iso/CONTINUOUS tiling
        # branch, which is wrong for a non-periodic ramp).
        samples = samples[:total]
        return self._finish(pd.DataFrame(samples, columns=self._ai_channels), rate)

    def _finish(self, raw_df: pd.DataFrame, sample_rate: float) -> pd.DataFrame:
        """Calibrate the raw AI frame and append the lock-in columns."""
        df = apply_calibration(
            raw_df,
            sample_rate=sample_rate,
            calibration=self._calibration,
            voltage_profiles=self._voltage_profiles,
            ai_channels=self._ai_channels,
        )
        # Lock-in: AC amplitude/phase of the temperature response. Only when
        # both frequency and amplitude are non-zero (else the bandwidth and
        # reference are undefined). Time-domain lock-in (not fft_demodulate)
        # because the DC base ramps, so the natural observable is per-sample
        # ``amp(t), phi(t)``.
        params = self._modulation or self._settings.modulation
        if params.lockin_capable and "temp-hr" in df.columns:
            amp, phase, valid = lockin_demodulate(
                df["temp-hr"].to_numpy(),
                sample_rate=sample_rate,
                frequency=params.frequency,
                return_valid=True,
            )
            df["temp-hr_amp"] = amp
            df["temp-hr_phase"] = phase
            # False over the lock-in settling transient at each edge (P1-9);
            # mask with this before averaging amp/phase.
            df["temp-hr_valid"] = valid
        return df


class IsoMode(BaseMode):
    """Static temperature with optional AC modulation, streamed via ring buffer.

    The user program for iso mode is degenerate: a constant value held for the
    requested duration. We accept the same ``time/temp_or_volt`` shape so the
    GUI code path can stay uniform, and we also accept the historical
    shorthand ``{"chN": {"volt": v}}`` (no ``time``), which is normalised
    into a 1 s constant program automatically.
    """

    name = "iso"

    def __init__(
        self,
        daq: DaqDeviceHandler,
        settings: BackSettings,
        calibration: Calibration,
        programs: Dict[str, dict],
        ai_channels: Sequence[int] = DEFAULT_AI_CHANNELS,
        modulation: Optional[ModulationParams] = None,
        modulation_channel: str = HEATER_AO,
        ring_buffer_seconds: float = 10.0,
    ) -> None:
        normalised: Dict[str, dict] = {}
        for ch, table in programs.items():
            if "time" in table:
                normalised[ch] = table
                continue
            if "volt" in table:
                value, kind = float(table["volt"]), "volt"
            elif "temp" in table:
                value, kind = float(table["temp"]), "temp"
            else:
                raise ValueError(
                    f"iso channel {ch} requires 'time'+'temp/volt' or shorthand "
                    f"'temp/volt' (got keys {list(table)})"
                )
            normalised[ch] = {"time": [0.0, 1000.0], kind: [value, value]}
        super().__init__(daq, settings, calibration, normalised, ai_channels=ai_channels)
        self._modulation = modulation
        self._modulation_channel = modulation_channel
        self._ring_buffer_seconds = ring_buffer_seconds
        # External abort handle. ``run()`` blocks on this; ``stop()`` from any
        # other thread (Tango command, GUI button) sets it to return early.
        self._stop_event = threading.Event()
        # AO buffer integrity diagnostic, populated by _build_profiles when AC
        # modulation is enabled. ``None`` means either DC-only or not armed.
        self._ao_period_report: Optional[AOPeriodReport] = None

    def stop(self) -> None:
        """Request a clean shutdown of the running scan from another thread."""
        self._stop_event.set()

    def _post_arm_check(self) -> None:
        # All programs must be constant in iso mode (no ramps).
        for ch, prog in self._programs.items():
            if not np.allclose(prog.values, prog.values[0]):
                raise ValueError(
                    f"IsoMode requires constant programs; channel {ch} is not."
                )

    def _build_profiles(self) -> Dict[str, np.ndarray]:
        params = self._modulation or self._settings.modulation
        if not params.enabled:
            # Pure DC: no scan needed, the manager will use ``ao_set``.
            # Route through ``_program_to_voltage`` so temperature programs get
            # converted via the calibration polynomial (and clipped to
            # ``[0, safe_voltage]``) and ``volt`` programs trigger the
            # over-safe-voltage warning. Without this, a degenerate iso DC
            # program like ``{"ch1": {"temp": 100}}`` would push the raw
            # 100.0 to the AO buffer (treated as volts) and fry the heater.
            return {
                ch: _program_to_voltage(prog, 1, self._calibration)
                for ch, prog in self._programs.items()
            }
        # AC modulation: build a single period repeated enough times to fill
        # the AO buffer of one second's worth of samples (CONTINUOUS scan).
        rate = self._settings.ao_params.sample_rate
        # One second of samples; AO scan is CONTINUOUS so the buffer keeps repeating.
        n = rate
        time_s = np.arange(n) / float(rate)
        profiles: Dict[str, np.ndarray] = {}
        for ch, prog in self._programs.items():
            base = np.full(n, _program_to_voltage(prog, n, self._calibration)[0])
            if ch == self._modulation_channel:
                base = apply_modulation(time_s, base, params)
                _clip_modulation_to_safe(base, self._calibration.safe_voltage, ch)
            profiles[ch] = base
        # Sanity check: the AO buffer is replayed CONTINUOUS, so a non-integer
        # number of AC cycles in the buffer would inject a phase jump at every
        # wrap (and visible spectral sidebands on the chip drive). With the
        # default 1-second buffer at f_mod=37.5 Hz this is exactly what
        # happens (37.5 cycles -> pi rad jump per wrap). We log a warning
        # rather than raise: the experiment still runs, just with biased C_p.
        # The fix in production is either to choose f_mod such that
        # ``rate / f_mod`` is rational with a small denominator that divides
        # ``n``, or to size the AO buffer to the smallest integer-cycle
        # length (see :func:`_integer_cycle_length` in shared.modulation).
        ac_profile = profiles.get(self._modulation_channel)
        if ac_profile is not None:
            report = check_ao_period_integrity(
                ac_profile, sample_rate=float(rate), frequency=params.frequency
            )
            self._ao_period_report = report
            if not report.seamless:
                logger.warning(
                    "IsoMode AO modulation buffer is NOT seamless: "
                    "%.3f cycles in buffer (drift %+.3f cycles -> "
                    "%+.4f rad phase jump per wrap), spectral leakage %.2f%%. "
                    "Choose f_mod so that buffer_samples * f_mod / sample_rate "
                    "is an integer (e.g. for fs=%.0f Hz pick f_mod from "
                    "{1, 2, 4, 5, 8, 10, 16, 20, 25, 40, 50, ...} Hz instead).",
                    report.cycles,
                    report.cycles_drift,
                    report.phase_jump_rad,
                    100.0 * report.leakage_fraction,
                    float(rate),
                )
        return profiles

    def _drive_ao(self, em: ExperimentManager) -> None:
        """Drive the armed iso AO profile on ``em``.

        DC profiles go through ``ao_set``; AC profiles through the CONTINUOUS
        ``ao_modulated`` buffer. Any prior AO drive is stopped first so a
        re-drive (switching setpoint, or going to 0 on "Off") cannot leave the
        previous CONTINUOUS scan latched on the heater.
        """
        em.stop_ao()
        params = self._modulation or self._settings.modulation
        if params.enabled:
            em.ao_modulated(self._voltage_profiles)
        else:
            for ch, profile in self._voltage_profiles.items():
                em.ao_set(channel_index(ch), float(profile[0]))

    def start_hold(self, em: ExperimentManager) -> None:
        """Start driving the armed iso AO profile and return immediately.

        The AO output is held until ``em.stop_ao()`` is called (or another
        profile is driven). AI is NOT started here -- the caller's persistent
        ring buffer keeps streaming, so the live plot stays alive. This is the
        "eternal iso / Set and hold" path (todo P1-5). A finite, auto-stopping
        iso program is the ``run(duration_seconds=...)`` path instead.
        """
        if not self.is_armed():
            raise RuntimeError("IsoMode is not armed; call arm() first")
        self._drive_ao(em)

    def run(
        self,
        duration_seconds: Optional[float] = None,
        em: Optional[ExperimentManager] = None,
        snapshot: Optional[Callable[[], np.ndarray]] = None,
    ) -> pd.DataFrame:
        """Stream AI until ``stop()`` or ``duration_seconds`` elapses.

        ``duration_seconds`` is a *maximum* timeout. ``None`` means "block
        until ``stop()`` is called" (used by long iso runs from the GUI).
        ``stop()`` from any other thread returns ``run()`` cleanly with
        whatever the ring buffer has captured so far.

        Two execution paths:

        * **Owned** (``em is None``, the default / legacy path): the mode
          creates its own :class:`ExperimentManager`, starts a private ring
          buffer, drives AO, snapshots, and tears everything down. Used by
          the Tango server and standalone scripts.
        * **Injected** (``em`` supplied, plus a ``snapshot`` callable): the
          mode drives AO on the *caller's* manager and reads AI from the
          caller's already-running persistent ring buffer (via ``snapshot``)
          without ever touching the AI scan. On stop it halts **only AO**
          (``stop_ao``), so the persistent live stream keeps running. This
          is how :class:`LocalDeviceController` keeps the GUI live plot
          alive during an iso run (todo P1-17, Approach C: iso only).
        """
        if not self.is_armed():
            raise RuntimeError("IsoMode is not armed; call arm() first")

        params = self._modulation or self._settings.modulation
        if duration_seconds is None and self.duration_seconds < 1.0:
            # Falling back to the armed duration is the legacy behaviour for
            # callers that did not specify one. ``< 1 s`` clearly was a default
            # placeholder, so go indefinite.
            duration_seconds = None
        elif duration_seconds is None:
            duration_seconds = self.duration_seconds

        # Re-arm the abort flag. A stale ``stop()`` from a previous run must
        # not leak into this one.
        self._stop_event.clear()

        injected = em is not None
        if not injected:
            em = ExperimentManager(self._daq, self._settings)
        try:
            self._drive_ao(em)

            if injected:
                # The caller owns a persistent ring buffer; do not start a
                # second AI scan. Just hold the AO drive for the duration.
                self._stop_event.wait(timeout=duration_seconds)
                samples = snapshot() if snapshot is not None else np.empty((0, 0), dtype=float)
            else:
                em.start_ring_buffer(self._ai_channels, max_seconds=self._ring_buffer_seconds)
                # Block until either the timeout expires or stop() is called.
                self._stop_event.wait(timeout=duration_seconds)
                em.stop_ring_buffer()
                samples = em.snapshot_ring_buffer()
        finally:
            if injected:
                # Drop only the AO drive; leave the caller's AI scan running.
                em.stop_ao()
            else:
                em.stop()

        if samples.size == 0:
            return pd.DataFrame(columns=["time", "Taux", "Thtr", "temp", "temp-hr"])

        df = pd.DataFrame(samples, columns=self._ai_channels)
        df = apply_calibration(
            df,
            sample_rate=self._settings.ai_params.sample_rate,
            calibration=self._calibration,
            voltage_profiles=self._voltage_profiles,
            ai_channels=self._ai_channels,
        )
        if params.lockin_capable and "temp-hr" in df.columns:
            ai_rate = float(self._settings.ai_params.sample_rate)
            temp_hr = df["temp-hr"].to_numpy()
            # Time-domain lock-in: per-sample amp/phase trace. Useful for
            # visual diagnostics (settling, drift) even in iso mode.
            amp, phase, valid = lockin_demodulate(
                temp_hr, sample_rate=ai_rate, frequency=params.frequency,
                return_valid=True,
            )
            df["temp-hr_amp"] = amp
            df["temp-hr_phase"] = phase
            df["temp-hr_valid"] = valid  # False over the settling edges (P1-9)
            # FFT demodulation: scalar amp/phase per harmonic over the
            # whole capture. In iso mode the response is stationary so a
            # single global estimate is the natural physical observable;
            # 2f/3f harmonics are extracted at no additional cost and are
            # used in AC calorimetry as a check on heater linearity.
            #
            # We keep both estimators on purpose: the FFT is bias-free over
            # an integer-cycle window, while the time-domain lock-in shows
            # transient behaviour. Disagreement between the two flags either
            # a thermal transient, a non-stationary signal, or a problem
            # with the AO modulation period (see ``_ao_period_report``).
            try:
                fft_result = fft_demodulate(
                    temp_hr,
                    sample_rate=ai_rate,
                    frequency=params.frequency,
                    harmonics=(1, 2, 3),
                )
                # Stash on df.attrs so callers can pick up the scalars
                # without bloating the per-sample DataFrame. (df.attrs does
                # not round-trip through HDF5; if persistence is needed,
                # log them at INFO and revisit when the iso HDF5 export
                # lands -- see TODO.md P2-9.)
                df.attrs["temp-hr_fft"] = {
                    h.harmonic: {"amplitude": h.amplitude, "phase": h.phase}
                    for h in fft_result.harmonics
                }
                df.attrs["temp-hr_fft_leakage"] = fft_result.leakage_fraction
                df.attrs["temp-hr_fft_window_samples"] = fft_result.window_samples
                fund = fft_result.fundamental
                logger.info(
                    "IsoMode FFT demod: 1f -> A=%.4g, phi=%+.4f rad; "
                    "leakage=%.2f%%, window=%d samples",
                    fund.amplitude, fund.phase,
                    100.0 * fft_result.leakage_fraction,
                    fft_result.window_samples,
                )
            except ValueError as exc:
                # Signal too short / Nyquist violation: log but do not
                # crash the run -- the time-domain lock-in still produced
                # something usable.
                logger.warning("IsoMode FFT demod skipped: %s", exc)
        return df


# ---------------------------------------------------------------------------
# Factory used by the Tango layer / scripts
# ---------------------------------------------------------------------------
MODE_REGISTRY = {
    FastHeat.name: FastHeat,
    SlowMode.name: SlowMode,
    IsoMode.name: IsoMode,
}


def create_mode(
    name: str,
    daq: DaqDeviceHandler,
    settings: BackSettings,
    calibration: Calibration,
    programs: Dict[str, dict],
    ai_channels: Sequence[int] = DEFAULT_AI_CHANNELS,
    **kwargs,
) -> BaseMode:
    """Instantiate a mode by string name. Raises ``KeyError`` for unknown modes."""
    if name not in MODE_REGISTRY:
        raise KeyError(
            f"Unknown mode {name!r}. Valid options: {sorted(MODE_REGISTRY)}"
        )
    cls = MODE_REGISTRY[name]
    return cls(daq, settings, calibration, programs, ai_channels=ai_channels, **kwargs)


# ---------------------------------------------------------------------------
# Persistence: write a run result to the legacy HDF5 layout
# ---------------------------------------------------------------------------
_EXP_DATA_COLUMNS = (
    "time",
    "Taux",
    "Thtr",
    "Uref",
    "temp",
    "temp-hr",
    "temp-hr_amp",
    "temp-hr_phase",
    "temp-hr_valid",
)


def save_run_to_h5(
    df: "pd.DataFrame",
    voltage_profiles: Dict[str, np.ndarray],
    programs: Dict[str, dict],
    calibration: Calibration,
    settings: BackSettings,
    path: str,
) -> None:
    """Write a finished run to ``path`` in the legacy ``exp_data.h5`` layout.

    The front-end downloads this file over HTTP and decodes it via the
    ``data`` group. We persist the same shape :class:`fastheat.FastHeat` and
    :class:`slow_mode.SlowMode` historically did (for backward compatibility),
    plus the AC lock-in columns when present (``temp-hr_amp`` / ``temp-hr_phase``
    / ``temp-hr_valid``, the last marking the lock-in settling edges).

    The Tango server calls this from ``run()`` — without it, ``run_fast_heat``
    completes silently but the file the front-end expects never appears.
    """
    import h5py
    import os

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with h5py.File(path, "w") as f:
        data = f.create_group("data")
        for col in _EXP_DATA_COLUMNS:
            if col in df.columns:
                data.create_dataset(col, data=np.asarray(df[col]))
        f.create_dataset("calibration", data=calibration.get_str())
        f.create_dataset("settings", data=settings.get_str())
        prog_group = f.create_group("temp_volt_programs")
        for chan, table in programs.items():
            program = prog_group.create_group(chan)
            if "time" in table:
                program.create_dataset("time", data=np.asarray(table["time"]))
                key = next(k for k in table if k != "time")
                program.create_dataset(key, data=np.asarray(table[key]))
            else:
                # Iso shorthand: ``{"chN": {"volt": 0.5}}`` -- record the
                # constant value as a single-element array; the front side
                # treats this as a flat program.
                for key, val in table.items():
                    program.create_dataset(key, data=np.asarray([val]))
        profiles_group = f.create_group("voltage_profiles")
        for chan, profile in voltage_profiles.items():
            profiles_group.create_dataset(chan, data=np.asarray(profile))


def finalize_raw_to_h5(
    raw_h5_path: str,
    out_h5_path: str,
    sample_rate: float,
    calibration: Calibration,
    settings: BackSettings,
    voltage_profiles: Dict[str, np.ndarray],
    programs: Dict[str, dict],
    ai_channels: Sequence[int] = DEFAULT_AI_CHANNELS,
    modulation: Optional[ModulationParams] = None,
    dataset: str = "raw_ai",
    block_rows: int = 200_000,
    program_offset: int = 0,
    tile_profile: bool = False,
) -> Optional[dict]:
    """Chunked calibrate: raw (U) recorder file -> separate calibrated (T) file.

    Streaming finalise (P1-17 step 4c-1): the multi-channel **raw AI (U, ADC
    volts)** is read from ``raw_h5_path`` in blocks of ``block_rows`` and written
    to a **separate** ``out_h5_path`` (the ``exp_data.h5`` layout) in engineering
    units, so the full multi-channel scan is **never held in RAM** -- only one
    block at a time. The raw (U) file is left intact for re-calibration.

    Two streaming passes:

    * **pass 1** accumulates the AD595 (cold-junction) mean over the whole scan
      (the only whole-scan quantity) -> ``Taux``;
    * **pass 2** calibrates each block with that ``Taux`` and a per-block
      ``Uref`` slice (the heater profile in ``voltage_profiles`` aligned to the
      raw via ``program_offset`` -- the ramp begins at raw row ``program_offset``,
      earlier rows are baseline with ``Uref = NaN``), appending the per-sample
      columns to extendable datasets.

    The AC lock-in (``temp-hr_amp/phase/valid``) needs the whole signal, so it
    runs once at the end over the (1-D) ``temp-hr`` column read back from the
    output -- the only non-bounded array here. Truly multi-day runs want a
    block-wise zero-phase lock-in instead (flagged refinement, P1-17).

    ``program_offset`` is the raw row where the AO program starts -- the
    DiskRecorder ``mark_index``. ``tile_profile`` selects how the heater profile
    maps to raw samples: ``False`` (slow ramp -- the profile spans the whole run)
    slices ``ref[idx]`` and marks rows past its end NaN; ``True`` (iso -- a short
    AO buffer replayed CONTINUOUS, or a DC constant) **tiles** it
    (``ref[idx % len]``) so every hold sample gets the commanded voltage, matching
    the whole-frame ``apply_calibration`` iso branch.

    Returns a summary dict ``{"path", "rows", "taux"}`` (no DataFrame -- the
    result lives on disk), or ``None`` if the raw file holds no samples.
    """
    import os
    import h5py

    if os.path.abspath(raw_h5_path) == os.path.abspath(out_h5_path):
        raise ValueError(
            "finalize_raw_to_h5: raw (U) and calibrated (T) paths must differ "
            f"(both {raw_h5_path!r}); the raw file must be preserved."
        )
    block_rows = max(1, int(block_rows))
    channels = list(ai_channels)
    nchan = len(channels)
    has_ref = HEATER_AO in voltage_profiles
    ref = np.asarray(voltage_profiles.get(HEATER_AO, []), dtype=float)
    per_sample = [c for c in _EXP_DATA_COLUMNS if not c.startswith("temp-hr_")]

    os.makedirs(os.path.dirname(os.path.abspath(out_h5_path)) or ".", exist_ok=True)
    with h5py.File(raw_h5_path, "r") as rf:
        if dataset not in rf:
            logger.warning("finalize_raw_to_h5: no '%s' dataset in %s (empty run)",
                           dataset, raw_h5_path)
            return None
        rds = cast("h5py.Dataset", rf[dataset])
        n = int(rds.shape[0])
        if n == 0:
            return None
        if int(rds.shape[1]) != nchan:
            raise ValueError(
                f"finalize_raw_to_h5: raw has {rds.shape[1]} channels but "
                f"ai_channels has {nchan} ({channels})"
            )

        # Pass 1: streaming AD595 mean -> Taux (the only whole-scan quantity).
        if AD595_AI in channels:
            pos = channels.index(AD595_AI)
            ssum, cnt = 0.0, 0
            for s in range(0, n, block_rows):
                col = np.asarray(rds[s:s + block_rows, pos], dtype=float)
                ssum += float(col.sum())
                cnt += int(col.shape[0])
            taux = float(calibration.hardware.correct_ad595(100.0 * (ssum / cnt))) if cnt else 0.0
        else:
            taux = 0.0

        # Pass 2: per-block calibrate -> append per-sample columns.
        with h5py.File(out_h5_path, "w") as of:
            data = of.create_group("data")
            dsets: Dict[str, "h5py.Dataset"] = {}
            written = 0
            for s in range(0, n, block_rows):
                block = np.asarray(rds[s:s + block_rows], dtype=float)
                m = int(block.shape[0])
                block_profiles: Dict[str, np.ndarray] = {}
                if has_ref:
                    idx = np.arange(s, s + m) - program_offset
                    uref = np.full(m, np.nan)
                    if ref.size:
                        if tile_profile:
                            # iso: short AO buffer replayed CONTINUOUS -> tile.
                            ok = idx >= 0
                            uref[ok] = ref[idx[ok] % ref.size]
                        else:
                            # slow ramp: profile spans the run -> slice.
                            ok = (idx >= 0) & (idx < ref.size)
                            uref[ok] = ref[idx[ok]]
                    block_profiles[HEATER_AO] = uref
                cal = apply_calibration(
                    pd.DataFrame(block, columns=channels),
                    sample_rate=sample_rate,
                    calibration=calibration,
                    voltage_profiles=block_profiles,
                    ai_channels=channels,
                    taux_override=taux,
                    sample_offset=s,
                )
                for col in per_sample:
                    if col not in cal.columns:
                        continue
                    arr = np.asarray(cal[col], dtype="float64")
                    if col not in dsets:
                        dsets[col] = data.create_dataset(
                            col, shape=(0,), maxshape=(None,), chunks=True, dtype="float64"
                        )
                    dsets[col].resize(written + m, axis=0)
                    dsets[col][written:written + m] = arr
                written += m

            # AC lock-in over the 1-D temp-hr column (read back once).
            if modulation is not None and modulation.lockin_capable and "temp-hr" in dsets:
                temphr = np.asarray(dsets["temp-hr"][:], dtype=float)
                amp, phase, valid = lockin_demodulate(
                    temphr, sample_rate=sample_rate,
                    frequency=modulation.frequency, return_valid=True,
                )
                for col, arr in (
                    ("temp-hr_amp", amp),
                    ("temp-hr_phase", phase),
                    ("temp-hr_valid", np.asarray(valid, dtype=float)),
                ):
                    data.create_dataset(col, data=np.asarray(arr, dtype="float64"))

            # Metadata groups (mirror save_run_to_h5).
            of.create_dataset("calibration", data=calibration.get_str())
            of.create_dataset("settings", data=settings.get_str())
            prog_group = of.create_group("temp_volt_programs")
            for chan, table in programs.items():
                pg = prog_group.create_group(chan)
                if "time" in table:
                    pg.create_dataset("time", data=np.asarray(table["time"]))
                    key = next(k for k in table if k != "time")
                    pg.create_dataset(key, data=np.asarray(table[key]))
                else:
                    for key, val in table.items():
                        pg.create_dataset(key, data=np.asarray([val]))
            prof_group = of.create_group("voltage_profiles")
            for chan, profile in voltage_profiles.items():
                prof_group.create_dataset(chan, data=np.asarray(profile))

    logger.info("finalize_raw_to_h5: %s (U, %d rows) -> %s (T), Taux=%.4g",
                raw_h5_path, n, out_h5_path, taux)
    return {"path": out_h5_path, "rows": int(written), "taux": float(taux)}


def read_calibrated_h5(
    path: str,
    columns: Optional[Sequence[str]] = None,
    step: int = 1,
    max_points: Optional[int] = None,
) -> Dict[str, np.ndarray]:
    """Read **decimated** columns from a calibrated (T) exp_data file (P1-17 4c-2).

    For the GUI result view, which must never load a full multi-hour record.
    Decimation is by **stride** -- keep every ``step``-th sample. If
    ``max_points`` is given it overrides ``step`` with ``ceil(rows / max_points)``
    so each returned column has at most ``max_points`` samples. (Stride keeps it
    simple; min/max-per-bin decimation that preserves narrow spikes is a future
    fidelity option.)

    Returns a dict of column name -> 1-D array (empty if the file has no
    ``data`` group or none of the requested columns).
    """
    import h5py

    result: Dict[str, np.ndarray] = {}
    with h5py.File(path, "r") as f:
        if "data" not in f:
            return result
        data = cast("h5py.Group", f["data"])
        avail = list(data.keys())
        cols = [c for c in (list(columns) if columns is not None else avail) if c in avail]
        if not cols:
            return result
        rows = int(cast("h5py.Dataset", data[cols[0]]).shape[0])
        stride = max(1, int(step))
        if max_points is not None and max_points > 0 and rows > max_points:
            stride = int(np.ceil(rows / max_points))
        for c in cols:
            result[c] = np.asarray(cast("h5py.Dataset", data[c])[::stride], dtype=float)
    return result


__all__ = [
    "DEFAULT_AI_CHANNELS",
    "BaseMode",
    "FastHeat",
    "SlowMode",
    "IsoMode",
    "create_mode",
    "apply_calibration",
    "save_run_to_h5",
    "finalize_raw_to_h5",
    "read_calibrated_h5",
    "segments_to_program",
    "ChannelProgram",
]
