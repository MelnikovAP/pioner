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
from typing import Dict, List, Optional, Sequence

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
from pioner.shared.settings import BackSettings
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
    if abs(total_ms % 1000.0) > 1e-6:
        # TODO(global): the AI buffer is currently sized to exactly one second.
        # That makes the half-buffer flip logic in
        # :meth:`ExperimentManager._collect_finite_ai` straightforward but
        # forces total program duration to be an integer number of seconds.
        # Lift this by sizing the buffer to ``ceil(seconds) * sample_rate``
        # and trimming the final tail to ``total_samples_per_channel``.
        raise ValueError(
            "Profile duration must be a whole number of seconds "
            f"(got {total_ms} ms). Adjust the program or change the buffer "
            "scheme in ExperimentManager._collect_finite_ai."
        )
    valid_keys = {channel_key(i) for i in range(ao_low, ao_high + 1)}
    bad_keys = set(programs) - valid_keys
    if bad_keys:
        raise ValueError(
            f"AO channel keys outside [{ao_low}, {ao_high}]: {sorted(bad_keys)}"
        )
    return float(total_ms)


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


# ---------------------------------------------------------------------------
# Calibration application: raw AI counts -> engineering units
# ---------------------------------------------------------------------------
def apply_calibration(
    raw: pd.DataFrame,
    sample_rate: float,
    calibration: Calibration,
    voltage_profiles: Dict[str, np.ndarray],
    ai_channels: Sequence[int] = DEFAULT_AI_CHANNELS,
) -> pd.DataFrame:
    """Convert raw AI samples into engineering units (Taux, Thtr, T, ...).

    The historical implementation lived in ``FastHeat._apply_calibration`` with
    several magic constants hard-coded. The amplifier gains and AD595
    correction polynomial are now read from
    :attr:`Calibration.hardware`.
    """
    df = raw.copy()
    if df.empty:
        return df

    # Time scale in ms.
    df["time"] = (np.arange(len(df)) * 1000.0) / sample_rate

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
    if AD595_AI in df.columns:
        u_aux = float(df[AD595_AI].mean())
        t_aux = 100.0 * u_aux
        t_aux = hw.correct_ad595(t_aux)
        df["Taux"] = t_aux
    else:
        df["Taux"] = 0.0

    # Thermopile temperature on the standard channel (Utpl) and on the
    # high-resolution modulation channel (Umod).
    if UTPL_AI in df.columns:
        df[UTPL_AI] = df[UTPL_AI] * (1000.0 / hw.gain_utpl)  # mV at front-end
        ax = df[UTPL_AI] + calibration.utpl0
        df["temp"] = (
            calibration.ttpl0 * ax + calibration.ttpl1 * (ax**2)
        )
        df["temp"] += df["Taux"]
    if UMOD_AI in df.columns:
        df[UMOD_AI] = df[UMOD_AI] * (1000.0 / hw.gain_umod)
        ax_hr = df[UMOD_AI] + calibration.utpl0
        df["temp-hr"] = (
            calibration.ttpl0 * ax_hr + calibration.ttpl1 * (ax_hr**2)
        )

    # Heater temperature derived from V/I.
    if UHTR_AI in df.columns and HEATER_CURRENT_AI in df.columns:
        df[UHTR_AI] = df[UHTR_AI] * 1000.0  # heater voltage in mV
        ih = calibration.ihtr0 + df[HEATER_CURRENT_AI] * calibration.ihtr1
        # When the heater is idle (current ~ 0) R_heater is undefined. The
        # historical implementation used 0 as a sentinel which then evaluated
        # to ``thtr0 + thtr1*thtrcorr + ...`` and produced a physically
        # meaningless number (~ -1070 °C with the production polynomial).
        # Mark those samples as NaN so downstream code / plots can skip them.
        nz = ih.abs() > 1e-9
        rhtr = pd.Series(np.full(len(df), np.nan), index=df.index)
        rhtr.loc[nz] = (
            (df.loc[nz, UHTR_AI] - df.loc[nz, HEATER_CURRENT_AI] * 1000.0
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

    # ------------------------------------------------------------------
    # Arming / introspection
    # ------------------------------------------------------------------
    def arm(self) -> None:
        """Validate inputs and build the AO voltage profiles."""
        ao = self._settings.ao_params
        self._duration_ms = _validate_programs(
            self._programs, ao.low_channel, ao.high_channel
        )
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
            result = em.finite_scan(
                self._voltage_profiles,
                self._ai_channels,
                seconds=int(self.duration_seconds),
            )
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
        # Clamp to the safe voltage envelope so we cannot saturate the heater.
        np.clip(
            profiles[self._modulation_channel],
            0.0,
            self._calibration.safe_voltage,
            out=profiles[self._modulation_channel],
        )
        return profiles

    def run(self) -> pd.DataFrame:
        if not self.is_armed():
            raise RuntimeError("SlowMode is not armed; call arm() first")

        with ExperimentManager(self._daq, self._settings) as em:
            result = em.finite_scan(
                self._voltage_profiles,
                self._ai_channels,
                seconds=int(self.duration_seconds),
            )
        df = apply_calibration(
            result.data,
            sample_rate=result.ai_rate,
            calibration=self._calibration,
            voltage_profiles=self._voltage_profiles,
            ai_channels=self._ai_channels,
        )

        # Lock-in: extract AC amplitude and phase of the temperature response.
        # Only run the lock-in if both frequency and amplitude are non-zero;
        # otherwise the bandwidth and reference are undefined.
        # We use the *time-domain* lock-in here (not fft_demodulate) because
        # SlowMode's DC base ramps across the scan, so the AC amplitude is a
        # function of T and the natural observable is per-sample
        # ``amp(t), phi(t)`` -- exactly what ``lockin_demodulate`` returns.
        # ``fft_demodulate`` would collapse the ramp into a single scalar
        # which is meaningless for slow mode.
        params = self._modulation or self._settings.modulation
        if params.lockin_capable and "temp-hr" in df.columns:
            amp, phase = lockin_demodulate(
                df["temp-hr"].to_numpy(),
                sample_rate=result.ai_rate,
                frequency=params.frequency,
            )
            df["temp-hr_amp"] = amp
            df["temp-hr_phase"] = phase
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
            return {ch: np.array([prog.values[0]]) for ch, prog in self._programs.items()}
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
                np.clip(base, 0.0, self._calibration.safe_voltage, out=base)
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

    def run(self, duration_seconds: Optional[float] = None) -> pd.DataFrame:
        """Stream AI until ``stop()`` or ``duration_seconds`` elapses.

        ``duration_seconds`` is a *maximum* timeout. ``None`` means "block
        until ``stop()`` is called" (used by long iso runs from the GUI).
        ``stop()`` from any other thread returns ``run()`` cleanly with
        whatever the ring buffer has captured so far.
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

        em = ExperimentManager(self._daq, self._settings)
        try:
            if params.enabled:
                em.ao_modulated(self._voltage_profiles)
            else:
                # Single-channel DC voltage on every channel mentioned in the program.
                for ch, profile in self._voltage_profiles.items():
                    em.ao_set(channel_index(ch), float(profile[0]))

            em.start_ring_buffer(self._ai_channels, max_seconds=self._ring_buffer_seconds)
            # Block until either the timeout expires or stop() is called.
            self._stop_event.wait(timeout=duration_seconds)
            em.stop_ring_buffer()

            samples = em.snapshot_ring_buffer()
        finally:
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
            amp, phase = lockin_demodulate(
                temp_hr, sample_rate=ai_rate, frequency=params.frequency,
            )
            df["temp-hr_amp"] = amp
            df["temp-hr_phase"] = phase
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
                # lands -- see todo.md P2-9.)
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


__all__ = [
    "DEFAULT_AI_CHANNELS",
    "BaseMode",
    "FastHeat",
    "SlowMode",
    "IsoMode",
    "create_mode",
    "apply_calibration",
    "ChannelProgram",
]
