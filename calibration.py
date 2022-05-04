from constants import JSON_EXTENSION
from settings_constants import *
import json
import os

# TODO: write unit tests for reading and writing any calibration file
# TODO: do we want to provide **public** access to all calibration attributes?

class Calibration:
    def __init__(self):
    # [Info]
        self.comment = 'no calibration'
    # [Modulation params]
        self.amplitude = 0.05
        self.offset = 0.1
        self.frequency = 75.
    # [Gains]
        self.urefgain = 1.
        self.umodgain = 2.
        self.utplgain = 5.
        self.uhtrgain = 10.
    # [Calibration coeff]
        # [Utpl] = [U(mv)] + utpl0
        self.utpl0 = 0.
        # [Ttpl] = ttpl0 * [Utpl] + ttpl1 * [Utpl^2]
        self.ttpl0 = 1.                 
        self.ttpl1 = 0.
        # [Thtr] = thtr0 + thtr1 * [R + thtrcorr] + thtr2 * [(R + thtrcorr)^2]
        self.thtr0 = 0.
        self.thtr1 = 1.
        self.thtr2 = 0.
        self.thtrcorr = 0
        # [Thtrd] = thtrd0 + thtrd1 * [R + thtrdcorr] + thtrd2 * [(R + thtrdcorr)^2]
        self.thtrd0 = 0.
        self.thtrd1 = 1.
        self.thtrd2 = 0.
        self.thtrdcorr = 0 
        # [Uhtr] = ([U(mv)] + uhtr0) * uhtr1
        self.uhtr0 = 0.
        self.uhtr1 = 1.
        # [Ihtr] = ihtr0 + ihtr1 * [I]
        self.ihtr0 = 0.
        self.ihtr1 = 1.
        # [Theater] = theater0 * [U] + theater1 * [U^2] + theater2 * [U^3]
        self.theater0 = 1.
        self.theater1 = 0.
        self.theater2 = 0.
        # [Amplitude correction] = ac0 + ac1 * [T] + ac2 * [T^2] + ac3 * [T^3]
        self.ac0 = 0.
        self.ac1 = 1.
        self.ac2 = 0.
        self.ac3 = 0.
        # [R heater]
        self.rhtr = 1700.  # TODO: check units
        # [Heater safe voltage]
        self.safe_voltage = 9.  # V

        self._add_params()

    def read(self, path: str):
        self._json_calib = dict()
        if not os.path.exists(path):
            raise ValueError("Calibration file doesn't exist.")
        if not os.path.splitext(path)[-1] != JSON_EXTENSION:
            raise ValueError("Calibration file doesn't have '{}' extension.".format(JSON_EXTENSION))
        with open(path, 'r') as f:
            self._json_calib = json.load(f)
        if not self._json_calib:
            raise ValueError("Empty calibration file defined.")

    # [Info]
        self.comment = self._json_calib[INFO_FIELD]
    # [Modulation params]
        self.amplitude = float(self._json_calib[MODULATION_PARAMS_FIELD][AMPLITUDE_FIELD])
        self.offset = float(self._json_calib[MODULATION_PARAMS_FIELD][OFFSET_FIELD])
        self.frequency = float(self._json_calib[MODULATION_PARAMS_FIELD][FREQUENCY_FIELD])
    # [Gains]
        self.urefgain = float(self._json_calib[GAINS_FIELD][U_REF_GAIN_FIELD])
        self.umodgain = float(self._json_calib[GAINS_FIELD][U_MOD_GAIN_FIELD])
        self.utplgain = float(self._json_calib[GAINS_FIELD][U_TPL_GAIN_FIELD])
        self.uhtrgain = float(self._json_calib[GAINS_FIELD][U_HTR_GAIN_FIELD])
    # [Calibration coeff]
        # [Utpl] = [U(mv)] + utpl0
        self.utpl0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][U_TPL_FIELD]['0'])
        # [Ttpl] = ttpl0 * [Utpl] + ttpl1 * [Utpl^2]
        self.ttpl0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_TPL_FIELD]['0'])
        self.ttpl1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_TPL_FIELD]['1'])
        # [Thtr] = thtr0 + thtr1 * [R + thtrcorr] + thtr2 * [(R + thtrcorr)^2]
        self.thtr0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD]['0'])
        self.thtr1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD]['1'])
        self.thtr2 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD]['2'])
        self.thtrcorr = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD][CORR_FIELD])
        # [Thtrd] = thtrd0 + thtrd1 * [R + thtrdcorr] + thtrd2 * [(R + thtrdcorr)^2]
        self.thtrd0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD]['0'])
        self.thtrd1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD]['1'])
        self.thtrd2 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD]['2'])
        self.thtrdcorr = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD][CORR_FIELD])
        # [Uhtr] = ([U(mv)] + uhtr0) * uhtr1
        self.uhtr0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][U_HTR_FIELD]['0'])
        self.uhtr1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][U_HTR_FIELD]['1'])
        # [Ihtr] = ihtr0 + ihtr1 * [I]
        self.ihtr0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][I_HTR_FIELD]['0'])
        self.ihtr1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][I_HTR_FIELD]['1'])
        # [Theater] = theater0 * [U] + theater1 * [U^2] + theater2 * [U^3]
        self.theater0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HEATER_FIELD]['0'])
        self.theater1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HEATER_FIELD]['1'])
        self.theater2 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][T_HEATER_FIELD]['2'])
        # [Amplitude correction] = ac0 + ac1 * [T] + ac2 * [T^2] + ac3 * [T^3]
        self.ac0 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['0'])
        self.ac1 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['1'])
        self.ac2 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['2'])
        self.ac3 = float(self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['3'])
        # [R heater]
        self.rhtr = float(self._json_calib[CALIBRATION_COEFFS_FIELD][R_HEATER_FIELD])
        # [Heater safe voltage]
        self.safe_voltage = float(self._json_calib[CALIBRATION_COEFFS_FIELD][HEATER_SAFE_VOLTAGE_FIELD])
        
        self._add_params()

    def write(self, path: str):
        # [Info]
        self._json_calib[INFO_FIELD] = self.comment
    # [Modulation params]
        self._json_calib[MODULATION_PARAMS_FIELD][AMPLITUDE_FIELD] = self.amplitude
        self._json_calib[MODULATION_PARAMS_FIELD][OFFSET_FIELD] = self.offset
        self._json_calib[MODULATION_PARAMS_FIELD][FREQUENCY_FIELD] = self.frequency
    # [Gains]
        self._json_calib[GAINS_FIELD][U_REF_GAIN_FIELD] = self.urefgain
        self._json_calib[GAINS_FIELD][U_MOD_GAIN_FIELD] = self.umodgain
        self._json_calib[GAINS_FIELD][U_TPL_GAIN_FIELD] = self.utplgain
        self._json_calib[GAINS_FIELD][U_HTR_GAIN_FIELD] = self.uhtrgain
    # [Calibration coeff]
        # [Utpl] = [U(mv)] + utpl0
        self._json_calib[CALIBRATION_COEFFS_FIELD][U_TPL_FIELD]['0'] = self.utpl0
        # [Ttpl] = ttpl0 * [Utpl] + ttpl1 * [Utpl^2]
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_TPL_FIELD]['0'] = self.ttpl0
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_TPL_FIELD]['1'] = self.ttpl1
        # [Thtr] = thtr0 + thtr1 * [R + thtrcorr] + thtr2 * [(R + thtrcorr)^2]
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD]['0'] = self.thtr0
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD]['1'] = self.thtr1
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD]['2'] = self.thtr2
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTR_FIELD][CORR_FIELD] = self.thtrcorr
        # [Thtrd] = thtrd0 + thtrd1 * [R + thtrdcorr] + thtrd2 * [(R + thtrdcorr)^2]
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD]['0'] = self.thtrd0
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD]['1'] = self.thtrd1
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD]['2'] = self.thtrd2
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HTRD_FIELD][CORR_FIELD] = self.thtrdcorr
        # [Uhtr] = ([U(mv)] + uhtr0) * uhtr1
        self._json_calib[CALIBRATION_COEFFS_FIELD][U_HTR_FIELD]['0'] = self.uhtr0
        self._json_calib[CALIBRATION_COEFFS_FIELD][U_HTR_FIELD]['1'] = self.uhtr1
        # [Ihtr] = ihtr0 + ihtr1 * [I]
        self._json_calib[CALIBRATION_COEFFS_FIELD][I_HTR_FIELD]['0'] = self.ihtr0
        self._json_calib[CALIBRATION_COEFFS_FIELD][I_HTR_FIELD]['1'] = self.ihtr1
        # [Theater] = theater0 * [U] + theater1 * [U^2] + theater2 * [U^3]
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HEATER_FIELD]['0'] = self.theater0
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HEATER_FIELD]['1'] = self.theater1
        self._json_calib[CALIBRATION_COEFFS_FIELD][T_HEATER_FIELD]['2'] = self.theater2
        # [Amplitude correction] = ac0 + ac1 * [T] + ac2 * [T^2] + ac3 * [T^3]
        self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['0'] = self.ac0
        self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['1'] = self.ac1
        self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['2'] = self.ac2
        self._json_calib[CALIBRATION_COEFFS_FIELD][AMPLITUDE_CORRECTION_FIELD]['3'] = self.ac3
        # [R heater]
        self._json_calib[CALIBRATION_COEFFS_FIELD][R_HEATER_FIELD] = self.rhtr
        # [Heater safe voltage]
        self._json_calib[CALIBRATION_COEFFS_FIELD][HEATER_SAFE_VOLTAGE_FIELD] = self.safe_voltage

        with open(path, 'w') as f:
            json.dump(self._json_calib, f, indent='\t')

    def _add_params(self):
        # parameters that are not in calibration file but need to use later
        self.max_temp = self.theater0 * self.safe_voltage + \
                        self.theater1 * (self.safe_voltage ** 2) + \
                        self.theater2 * (self.safe_voltage ** 3)  # TODO: move calculation to another function
        self.min_temp = 0.


if __name__ == '__main__':
    try:
        calib = Calibration()
        print(calib.max_temp)
        calib.read('./calibration.json')
        print(calib.max_temp)
    except BaseException as e:
        print(e)
