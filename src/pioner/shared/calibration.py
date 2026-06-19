"""Chip-level and hardware calibration container.

The :class:`Calibration` object stores the polynomial coefficients used to
translate raw analog-input voltages into physical quantities (temperature,
heater current, ...) and also a small number of *hardware* fields that
describe the analog conditioning electronics (instrumentation amplifier
gains, AD595 thermocouple correction polynomial, etc.). Storing these next to
the chip-specific coefficients keeps everything that the experiment manager
needs in one place.

JSON layout (see ``src/pioner/settings/default_calibration.json``)::

    {
      "Info": "...",
      "Calibration coeff": {
        "Utpl": {"0": ...},
        "Ttpl": {"0": ..., "1": ...},
        "Thtr": {"0": ..., "1": ..., "2": ..., "corr": ...},
        "Thtrd": {...},
        "Uhtr": {"0": ..., "1": ...},
        "Ihtr": {"0": ..., "1": ...},
        "Theater": {"0": ..., "1": ..., "2": ...},
        "Amplitude correction": {"0": ..., "1": ..., "2": ..., "3": ...},
        "R heater": ...,
        "R guard": ...,
        "Heater safe voltage": ...,
        "Hardware": {                     # NEW (optional, has defaults)
          "Gain Utpl": 11.0,             # instrumentation amplifier gain on Utpl channel
          "Gain Umod": 121.0,            # high-resolution Umod amplifier gain
          "AD595 low correction": [2.6843, 1.2709, 0.0042867, 3.4944e-05]
        }
      }
    }

Reading is forgiving: if ``Hardware`` is missing, sensible defaults are used.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional

from pioner.shared.constants import (
    AMPLITUDE_CORRECTION_ENABLED_FIELD,
    AMPLITUDE_CORRECTION_FIELD,
    CALIBRATION_COEFFS_FIELD,
    CORR_FIELD,
    DEFAULT_CALIBRATION_FILE_REL_PATH,
    HARDWARE_FIELD,
    HARDWARE_AD595_LOW_FIELD,
    HARDWARE_GAIN_UMOD_FIELD,
    HARDWARE_GAIN_UTPL_FIELD,
    HEATER_SAFE_VOLTAGE_FIELD,
    INFO_FIELD,
    I_HTR_FIELD,
    JSON_EXTENSION,
    R_GUARD_FIELD,
    R_HEATER_BROKEN_FIELD,
    R_HEATER_FIELD,
    R_HEATER_SHORTED_FIELD,
    T_HEATER_FIELD,
    T_HTRD_FIELD,
    T_HTR_FIELD,
    T_TPL_FIELD,
    U_HTR_FIELD,
    U_TPL_FIELD,
)


def _ensure_json_extension(path: str) -> None:
    """Raise ``ValueError`` unless ``path`` ends with ``.json`` (case-insensitive)."""
    ext = os.path.splitext(path)[-1].lower().lstrip(".")
    if ext != JSON_EXTENSION:
        raise ValueError(
            f"Calibration file '{path}' must have '.{JSON_EXTENSION}' extension."
        )


@dataclass
class HardwareCalibration:
    """Constants describing the conditioning electronics, not the chip."""

    #: Instrumentation amplifier gain on the standard thermopile channel (Utpl).
    gain_utpl: float = 11.0
    #: Gain on the high-resolution modulation channel (Umod).
    gain_umod: float = 121.0
    #: AD595 cold-junction correction polynomial valid below -12 °C
    #: (T_corrected = c0 + c1*T + c2*T^2 + c3*T^3).
    ad595_low_correction: List[float] = field(
        default_factory=lambda: [2.6843, 1.2709, 0.0042867, 3.4944e-05]
    )

    def correct_ad595(self, temp_c: float) -> float:
        """Apply the AD595 cold-junction correction below -12 °C, identity above."""
        if temp_c >= -12.0:
            return temp_c
        c0, c1, c2, c3 = self.ad595_low_correction
        return c0 + c1 * temp_c + c2 * temp_c**2 + c3 * temp_c**3


class Calibration:
    """Holds chip + hardware calibration coefficients.

    Default-constructed instances act as an *identity* calibration: voltage and
    temperature pass through unchanged, useful as a fallback or for unit
    tests.
    """

    def __init__(self) -> None:
        # [Info]
        self.comment: str = "no calibration"

        # [Calibration coeff]
        # [Utpl] = [U(mv)] + utpl0
        self.utpl0: float = 0.0
        # [Ttpl] = ttpl0 * [Utpl] + ttpl1 * [Utpl^2]
        self.ttpl0: float = 1.0
        self.ttpl1: float = 0.0
        # [Thtr] = thtr0 + thtr1 * [R + thtrcorr] + thtr2 * [(R + thtrcorr)^2]
        self.thtr0: float = 0.0
        self.thtr1: float = 1.0
        self.thtr2: float = 0.0
        self.thtrcorr: float = 0.0
        # Same shape for the differential heater (Thtrd).
        self.thtrd0: float = 0.0
        self.thtrd1: float = 1.0
        self.thtrd2: float = 0.0
        self.thtrdcorr: float = 0.0
        # Heater voltage offset/gain applied inside the Rhtr formula.
        # ``uhtr0`` is in **volts** (matches the V-domain numerator after the
        # bug-fix to apply_calibration).
        self.uhtr0: float = 0.0
        self.uhtr1: float = 1.0
        # Heater current proxy: ``Ihtr = ihtr0 + ihtr1 * V_ch0``. AI ch0 is a
        # voltage proxy for the heater current (the node between the series
        # resistor and the amplifier loop), NOT a shunt voltage with a known
        # R_shunt. Production calibration uses the dimensionless identity
        # ``ihtr0 = 0``, ``ihtr1 = 1`` so ``ih = V_ch0`` in volts; the Thtr
        # polynomial is fitted against this proxy directly (Rhtr comes out
        # V/V, not ohms). Proper SI calibration (``ihtr1 ~= 1/R_shunt`` for
        # amperes) is tracked in todo P2-21; see the matching comment in
        # ``modes.apply_calibration``.
        self.ihtr0: float = 0.0
        self.ihtr1: float = 1.0
        # [Theater] = theater0 * U + theater1 * U^2 + theater2 * U^3
        self.theater0: float = 1.0
        self.theater1: float = 0.0
        self.theater2: float = 0.0
        # [Amplitude correction] (used by lock-in for AC experiments)
        # kamp(T) = ac0 + ac1*T + ac2*T^2 + ac3*T^3; the demodulated lock-in
        # amplitude is divided by it when ``amplitude_correction_enabled`` is
        # set (P1-32). NOTE: these defaults give kamp(T) = T, which is a
        # placeholder, NOT a no-op -- a true no-op is ac0=1 (kamp==1). The
        # divider is therefore off by default so the placeholder cannot corrupt
        # the amplitude; enable it only with a calibration whose ac* are fitted.
        self.ac0: float = 0.0
        self.ac1: float = 1.0
        self.ac2: float = 0.0
        self.ac3: float = 0.0
        self.amplitude_correction_enabled: bool = False
        # Heater / guard reference resistances (Ohm).
        self.rhtr: float = 1700.0
        self.rghtr: float = 2300.0
        # Broken/shorted heater thresholds (P2-24), in the dimensionless proxy
        # domain of ``modes.heater_resistance`` (V/V, NOT ohms). Diagnostic only
        # (see ``classify_heater_resistance``); defaults are conservative
        # starting values from Bondar uCal (9000/50) -- the production proxy R is
        # numerically ohm-like at room temperature, but the real thresholds are
        # chip-specific and must be tuned on the bench. Never gate a run on them
        # from a guessed value.
        self.r_heater_broken: float = 9000.0
        self.r_heater_shorted: float = 50.0
        # Maximum DC voltage allowed on the heater AO channel (V).
        self.safe_voltage: float = 8.0

        # Hardware-side conditioning calibration (electronics, not chip).
        self.hardware: HardwareCalibration = HardwareCalibration()

        self._json_calib: Optional[dict] = None
        self._add_params()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def read(self, path: str) -> None:
        """Load coefficients from a JSON file, raising on any structural error."""
        if not os.path.exists(path):
            raise ValueError(f"Calibration file '{path}' does not exist.")
        _ensure_json_extension(path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            raise ValueError(f"Calibration file '{path}' is empty.")
        if CALIBRATION_COEFFS_FIELD not in data:
            raise ValueError(
                f"Calibration file '{path}' missing '{CALIBRATION_COEFFS_FIELD}' field."
            )

        self._json_calib = data
        coeffs = data[CALIBRATION_COEFFS_FIELD]

        self.comment = data.get(INFO_FIELD, "no calibration")

        self.utpl0 = float(coeffs[U_TPL_FIELD]["0"])

        self.ttpl0 = float(coeffs[T_TPL_FIELD]["0"])
        self.ttpl1 = float(coeffs[T_TPL_FIELD]["1"])

        self.thtr0 = float(coeffs[T_HTR_FIELD]["0"])
        self.thtr1 = float(coeffs[T_HTR_FIELD]["1"])
        self.thtr2 = float(coeffs[T_HTR_FIELD]["2"])
        self.thtrcorr = float(coeffs[T_HTR_FIELD][CORR_FIELD])

        self.thtrd0 = float(coeffs[T_HTRD_FIELD]["0"])
        self.thtrd1 = float(coeffs[T_HTRD_FIELD]["1"])
        self.thtrd2 = float(coeffs[T_HTRD_FIELD]["2"])
        self.thtrdcorr = float(coeffs[T_HTRD_FIELD][CORR_FIELD])

        self.uhtr0 = float(coeffs[U_HTR_FIELD]["0"])
        self.uhtr1 = float(coeffs[U_HTR_FIELD]["1"])

        self.ihtr0 = float(coeffs[I_HTR_FIELD]["0"])
        self.ihtr1 = float(coeffs[I_HTR_FIELD]["1"])

        self.theater0 = float(coeffs[T_HEATER_FIELD]["0"])
        self.theater1 = float(coeffs[T_HEATER_FIELD]["1"])
        self.theater2 = float(coeffs[T_HEATER_FIELD]["2"])

        self.ac0 = float(coeffs[AMPLITUDE_CORRECTION_FIELD]["0"])
        self.ac1 = float(coeffs[AMPLITUDE_CORRECTION_FIELD]["1"])
        self.ac2 = float(coeffs[AMPLITUDE_CORRECTION_FIELD]["2"])
        self.ac3 = float(coeffs[AMPLITUDE_CORRECTION_FIELD]["3"])
        # Optional opt-in switch; absent in legacy files -> stays off.
        self.amplitude_correction_enabled = bool(
            coeffs[AMPLITUDE_CORRECTION_FIELD].get(
                AMPLITUDE_CORRECTION_ENABLED_FIELD, False
            )
        )

        self.rhtr = float(coeffs[R_HEATER_FIELD])
        self.rghtr = float(coeffs[R_GUARD_FIELD])
        # Optional broken/shorted thresholds; absent in legacy files -> defaults.
        self.r_heater_broken = float(
            coeffs.get(R_HEATER_BROKEN_FIELD, self.r_heater_broken)
        )
        self.r_heater_shorted = float(
            coeffs.get(R_HEATER_SHORTED_FIELD, self.r_heater_shorted)
        )
        self.safe_voltage = float(coeffs[HEATER_SAFE_VOLTAGE_FIELD])

        # Optional hardware block; falls back to factory defaults.
        hw = coeffs.get(HARDWARE_FIELD, {})
        self.hardware = HardwareCalibration(
            gain_utpl=float(hw.get(HARDWARE_GAIN_UTPL_FIELD, 11.0)),
            gain_umod=float(hw.get(HARDWARE_GAIN_UMOD_FIELD, 121.0)),
            ad595_low_correction=list(
                hw.get(
                    HARDWARE_AD595_LOW_FIELD,
                    [2.6843, 1.2709, 0.0042867, 3.4944e-05],
                )
            ),
        )

        self._add_params()

    def write(self, path: str) -> None:
        """Persist the current calibration as JSON."""
        _ensure_json_extension(path)
        out = {
            INFO_FIELD: self.comment,
            CALIBRATION_COEFFS_FIELD: {
                U_TPL_FIELD: {"0": self.utpl0},
                T_TPL_FIELD: {"0": self.ttpl0, "1": self.ttpl1},
                T_HTR_FIELD: {
                    "0": self.thtr0,
                    "1": self.thtr1,
                    "2": self.thtr2,
                    CORR_FIELD: self.thtrcorr,
                },
                T_HTRD_FIELD: {
                    "0": self.thtrd0,
                    "1": self.thtrd1,
                    "2": self.thtrd2,
                    CORR_FIELD: self.thtrdcorr,
                },
                U_HTR_FIELD: {"0": self.uhtr0, "1": self.uhtr1},
                I_HTR_FIELD: {"0": self.ihtr0, "1": self.ihtr1},
                T_HEATER_FIELD: {
                    "0": self.theater0,
                    "1": self.theater1,
                    "2": self.theater2,
                },
                AMPLITUDE_CORRECTION_FIELD: {
                    "0": self.ac0,
                    "1": self.ac1,
                    "2": self.ac2,
                    "3": self.ac3,
                    AMPLITUDE_CORRECTION_ENABLED_FIELD: self.amplitude_correction_enabled,
                },
                R_HEATER_FIELD: self.rhtr,
                R_GUARD_FIELD: self.rghtr,
                R_HEATER_BROKEN_FIELD: self.r_heater_broken,
                R_HEATER_SHORTED_FIELD: self.r_heater_shorted,
                HEATER_SAFE_VOLTAGE_FIELD: self.safe_voltage,
                HARDWARE_FIELD: {
                    HARDWARE_GAIN_UTPL_FIELD: self.hardware.gain_utpl,
                    HARDWARE_GAIN_UMOD_FIELD: self.hardware.gain_umod,
                    HARDWARE_AD595_LOW_FIELD: list(self.hardware.ad595_low_correction),
                },
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent="\t")

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------
    def kamp(self, temp):
        """AC amplitude-correction gain ``kamp(T) = ac0 + ac1*T + ac2*T^2 + ac3*T^3``.

        ``temp`` is in degrees Celsius (the heater temperature ``Thtr`` in the
        runtime pipeline, matching how the ``ac*`` coefficients are fitted in
        Bondar uCal). Accepts a scalar, numpy array, or pandas Series and
        returns the same shape. The demodulated lock-in amplitude is *divided*
        by this factor (P1-32); see ``back.modes`` for the runtime guard that
        skips non-positive / non-finite ``kamp``.
        """
        t = temp
        return self.ac0 + self.ac1 * t + self.ac2 * t**2 + self.ac3 * t**3

    def classify_heater_resistance(self, rhtr: float) -> str:
        """Classify a proxy heater resistance as ``ok`` / ``broken`` / ``shorted``
        / ``unknown`` (P2-24).

        ``rhtr`` is the dimensionless proxy from ``modes.heater_resistance``
        (V/V). ``broken`` = open / no contact (R above ``r_heater_broken``);
        ``shorted`` = R below ``r_heater_shorted``; ``unknown`` = not finite
        (e.g. NaN at idle when no heater current flows). Diagnostic only -- it
        does NOT gate a run; the thresholds are bench-tunable starting values.
        """
        import math

        if rhtr is None or not math.isfinite(rhtr):
            return "unknown"
        if rhtr > self.r_heater_broken:
            return "broken"
        if rhtr < self.r_heater_shorted:
            return "shorted"
        return "ok"

    @staticmethod
    def solve_rhcorr(
        c0: float,
        c1: float,
        c2: float,
        r_measured: float,
        t_target: float,
        *,
        corr_start: float = 0.0,
        gain: float = 0.1,
        tol: float = 0.01,
        max_iter: int = 1000,
    ) -> dict:
        """In-situ R-correction auto-zero (P1-33), faithful to Bondar uCal.

        Damped fixed-point iteration (Unit1.cpp:1308-1342) that trims the
        additive resistance correction ``corr`` so the heater-temperature
        polynomial ``T(corr) = c0 + c1*(R+corr) + c2*(R+corr)^2`` agrees with the
        independent operating-point temperature ``t_target`` (= ``Ttpl + Taux``)
        at the measured resistance ``r_measured``:

            err = t_target - T(corr);  corr += gain * err   (gain 0.1)

        Stops when ``|err| < tol`` (0.01 C). If ``|err|`` ever exceeds 10000 C
        the iteration is diverging and ``corr`` is reset to 0 (Bondar's guard).
        Starts from ``corr_start`` (the current stored correction), matching
        Bondar which refines the existing ``Rhcorr`` rather than resetting it.

        Returns a report dict: ``corr`` (new correction), ``residual_c`` (final
        ``err`` in C), ``iterations``, ``converged`` (bool), ``diverged``
        (bool). ``r_measured`` must be finite and non-zero; otherwise the
        correction is left at ``corr_start`` and ``converged`` is False.
        """
        import math

        if not math.isfinite(r_measured) or r_measured == 0.0 or not math.isfinite(t_target):
            return {
                "corr": float(corr_start),
                "residual_c": float("nan"),
                "iterations": 0,
                "converged": False,
                "diverged": False,
            }
        corr = float(corr_start)
        err = float("nan")
        converged = False
        diverged = False
        iterations = 0
        for iterations in range(1, max_iter + 1):
            thtr = c0 + c1 * (r_measured + corr) + c2 * (r_measured + corr) ** 2
            err = t_target - thtr
            if abs(err) < tol:
                converged = True
                break
            if abs(err) > 10000.0:
                corr = 0.0
                diverged = True
                break
            corr += err * gain
        return {
            "corr": float(corr),
            "residual_c": float(err),
            "iterations": int(iterations),
            "converged": bool(converged),
            "diverged": bool(diverged),
        }

    def compute_rhcorr(
        self,
        r_measured: float,
        t_target: float,
        *,
        differential: bool = False,
        gain: float = 0.1,
        tol: float = 0.01,
        max_iter: int = 1000,
    ) -> dict:
        """Run :meth:`solve_rhcorr` for the heater (or differential heater) and
        store the result in ``self.thtrcorr`` (or ``self.thtrdcorr``).

        ``r_measured`` is the operating-point proxy resistance (mean of
        ``modes.heater_resistance`` over valid samples); ``t_target`` is the
        operating-point ``Ttpl + Taux`` (mean ``temp``). Mutates this
        Calibration; the caller persists it (e.g. via :meth:`write`). The
        returned report adds ``corr_old`` and ``field`` for display.
        """
        if differential:
            c0, c1, c2, corr_old = self.thtrd0, self.thtrd1, self.thtrd2, self.thtrdcorr
            field = "thtrdcorr"
        else:
            c0, c1, c2, corr_old = self.thtr0, self.thtr1, self.thtr2, self.thtrcorr
            field = "thtrcorr"
        report = self.solve_rhcorr(
            c0, c1, c2, r_measured, t_target,
            corr_start=corr_old, gain=gain, tol=tol, max_iter=max_iter,
        )
        if differential:
            self.thtrdcorr = report["corr"]
        else:
            self.thtrcorr = report["corr"]
        report["corr_old"] = float(corr_old)
        report["field"] = field
        return report

    def _add_params(self) -> None:
        """Compute derived parameters (e.g. clamping range for T<->V conversion)."""
        v = self.safe_voltage
        self.max_temp = self.theater0 * v + self.theater1 * v**2 + self.theater2 * v**3
        self.min_temp = 0.0

    def get_str(self) -> str:
        """Return a JSON-serialisable string representation (Tango pipe friendly)."""
        # Build a flat dict similar to the historical format used by the front
        # end (it just wants attribute names that match the Calibration fields).
        flat = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        flat["hardware"] = {
            "gain_utpl": self.hardware.gain_utpl,
            "gain_umod": self.hardware.gain_umod,
            "ad595_low_correction": list(self.hardware.ad595_low_correction),
        }
        return json.dumps(flat)


if __name__ == "__main__":
    cal = Calibration()
    cal.read(DEFAULT_CALIBRATION_FILE_REL_PATH)
    print(cal.get_str())
