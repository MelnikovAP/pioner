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
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from pioner.shared.calibration import Calibration
from pioner.shared.modulation import (
    ModulationParams,
    apply_modulation,
    lockin_demodulate,
)
from pioner.shared.settings import BackSettings
from pioner.shared.utils import temperature_to_voltage
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.experiment_manager import ExperimentManager, ScanResult

logger = logging.getLogger(__name__)


# Indices of the AI channels we always keep, in the order the analysis code
# below expects them. ``5`` is the heater voltage feedback, ``4`` the
# thermopile, ``3`` the AD595 cold-junction, ``1`` the modulation channel,
# ``0`` the current shunt.
DEFAULT_AI_CHANNELS = (0, 1, 3, 4, 5)


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
    valid_keys = {f"ch{i}" for i in range(ao_low, ao_high + 1)}
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
    """Interpolate and, if needed, convert temperature -> voltage."""
    arr = _interpolate_program(program, samples_per_channel)
    if program.is_temperature:
        arr = temperature_to_voltage(arr, calibration)
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
    if 3 in df.columns:
        u_aux = float(df[3].mean())
        t_aux = 100.0 * u_aux
        t_aux = hw.correct_ad595(t_aux)
        df["Taux"] = t_aux
    else:
        df["Taux"] = 0.0

    # Thermopile temperature on the standard channel (4) and on the
    # high-resolution modulation channel (1).
    if 4 in df.columns:
        df[4] = df[4] * (1000.0 / hw.gain_utpl)  # mV at the front-end input
        ax = df[4] + calibration.utpl0
        df["temp"] = (
            calibration.ttpl0 * ax + calibration.ttpl1 * (ax**2)
        )
        df["temp"] += df["Taux"]
    if 1 in df.columns:
        df[1] = df[1] * (1000.0 / hw.gain_umod)
        ax_hr = df[1] + calibration.utpl0
        df["temp-hr"] = (
            calibration.ttpl0 * ax_hr + calibration.ttpl1 * (ax_hr**2)
        )

    # Heater temperature derived from V/I.
    if 5 in df.columns and 0 in df.columns:
        df[5] = df[5] * 1000.0  # heater voltage in mV
        ih = calibration.ihtr0 + df[0] * calibration.ihtr1
        rhtr = pd.Series(np.zeros(len(df)), index=df.index)
        nz = ih.abs() > 1e-9
        rhtr.loc[nz] = (
            (df.loc[nz, 5] - df.loc[nz, 0] * 1000.0 + calibration.uhtr0)
            * calibration.uhtr1
            / ih.loc[nz]
        )
        thtr = (
            calibration.thtr0
            + calibration.thtr1 * (rhtr + calibration.thtrcorr)
            + calibration.thtr2 * ((rhtr + calibration.thtrcorr) ** 2)
        )
        df["Thtr"] = thtr

    # Provide the reference (guard) AO trace for context.
    if "ch1" in voltage_profiles:
        ref = np.asarray(voltage_profiles["ch1"], dtype=float)
        # Match length to the AI frame; if AI has a remainder, pad with NaN.
        if ref.size >= len(df):
            df["Uref"] = ref[: len(df)]
        else:
            padded = np.full(len(df), np.nan)
            padded[: ref.size] = ref
            df["Uref"] = padded

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
        modulation_channel: str = "ch1",
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
        modulation_channel: str = "ch1",
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
        return profiles

    def run(self, duration_seconds: Optional[float] = None) -> pd.DataFrame:
        """Stream AI for ``duration_seconds`` and return the demodulated frame.

        TODO(global): currently the wait is a plain ``time.sleep`` and there is
        no externally-visible interrupt handle. For long iso runs (minutes /
        hours) we should expose a ``threading.Event`` (or a dedicated
        ``stop()`` method) that the GUI / Tango layer can flip without having
        to wait for the duration to expire.
        """
        if not self.is_armed():
            raise RuntimeError("IsoMode is not armed; call arm() first")

        params = self._modulation or self._settings.modulation
        if duration_seconds is None:
            duration_seconds = max(self.duration_seconds, 1.0)

        em = ExperimentManager(self._daq, self._settings)
        try:
            if params.enabled:
                em.ao_modulated(self._voltage_profiles)
            else:
                # Single-channel DC voltage on every channel mentioned in the program.
                for ch, profile in self._voltage_profiles.items():
                    channel = int(ch.replace("ch", ""))
                    em.ao_set(channel, float(profile[0]))

            em.start_ring_buffer(self._ai_channels, max_seconds=self._ring_buffer_seconds)
            import time as _time

            _time.sleep(duration_seconds)
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
            amp, phase = lockin_demodulate(
                df["temp-hr"].to_numpy(),
                sample_rate=float(self._settings.ai_params.sample_rate),
                frequency=params.frequency,
            )
            df["temp-hr_amp"] = amp
            df["temp-hr_phase"] = phase
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
