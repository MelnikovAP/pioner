"""Chip-level and hardware calibration container.

The :class:`Calibration` object stores the polynomial coefficients used to
translate raw analog-input voltages into physical quantities (temperature,
heater current, ...) and also a small number of *hardware* fields that
describe the analog conditioning electronics (instrumentation amplifier
gains, AD595 thermocouple correction polynomial, etc.). Storing these next to
the chip-specific coefficients keeps everything that the experiment manager
needs in one place.

JSON layout (see ``settings/default_calibration.json``)::

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
    AMPLITUDE_CORRECTION_FIELD,
    CALIBRATION_COEFFS_FIELD,
    CORR_FIELD,
    HARDWARE_FIELD,
    HARDWARE_AD595_LOW_FIELD,
    HARDWARE_GAIN_UMOD_FIELD,
    HARDWARE_GAIN_UTPL_FIELD,
    HEATER_SAFE_VOLTAGE_FIELD,
    INFO_FIELD,
    I_HTR_FIELD,
    JSON_EXTENSION,
    R_GUARD_FIELD,
    R_HEATER_FIELD,
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
        # Heater current is derived from the shunt voltage: ``Ihtr = ihtr0 +
        # ihtr1 * V_shunt``. The ``ihtr1`` argument is therefore the shunt
        # admittance in **siemens** (1/R_shunt). The default identity
        # ``ihtr1 = 1.0`` is dimensionally meaningless (test fallback only);
        # production must set ``ihtr1 ~= 1/R_shunt`` so ``ih`` is in amperes
        # (see todo P0-3).
        self.ihtr0: float = 0.0
        self.ihtr1: float = 1.0
        # [Theater] = theater0 * U + theater1 * U^2 + theater2 * U^3
        self.theater0: float = 1.0
        self.theater1: float = 0.0
        self.theater2: float = 0.0
        # [Amplitude correction] (used by lock-in for AC experiments)
        self.ac0: float = 0.0
        self.ac1: float = 1.0
        self.ac2: float = 0.0
        self.ac3: float = 0.0
        # Heater / guard reference resistances (Ohm).
        self.rhtr: float = 1700.0
        self.rghtr: float = 2300.0
        # Maximum DC voltage allowed on the heater AO channel (V).
        self.safe_voltage: float = 9.0

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

        self.rhtr = float(coeffs[R_HEATER_FIELD])
        self.rghtr = float(coeffs[R_GUARD_FIELD])
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
                },
                R_HEATER_FIELD: self.rhtr,
                R_GUARD_FIELD: self.rghtr,
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
    cal.read("./settings/default_calibration.json")
    print(cal.get_str())
