import json
import os
import pandas as pd
import numpy as np

from pioner_app.core.constants import *

# TODO: write unit tests for reading and writing any calibration file
# TODO: do we want to provide **public** access to all calibration attributes?

class Calibration:
    def __init__(self):
    # [Info]
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        self.comment = 'no calibration'
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
        self.rghtr = 2300.  # TODO: check units
        # [Heater safe voltage]
        self.safe_voltage = 9.  # V

        self._add_params()
    def to_dict(self):
        """Преобразовать объект Calibration в словарь."""
        return {
            "comment": self.comment,
            "utpl0": self.utpl0,
            "ttpl0": self.ttpl0,
            "ttpl1": self.ttpl1,
            "uhtr0": self.uhtr0,
            "uhtr1": self.uhtr1,
            "ihtr0": self.ihtr0,
            "ihtr1": self.ihtr1,
            "thtr0": self.thtr0,
            "thtr1": self.thtr1,
            "thtr2": self.thtr2,
            "thtrd0": self.thtrd0,
            "thtrd1": self.thtrd1,
            "thtrd2": self.thtrd2,
            "safe_voltage": self.safe_voltage,
            "theater0": self.theater0,
            "theater1": self.theater1,
            "theater2": self.theater2,
            "rhtr": self.rhtr,
            "rghtr": self.rghtr,
            "ac0": self.ac0,
            "ac1": self.ac1,
            "ac2": self.ac2,
            "ac3": self.ac3,
        }

    def to_file_dict(self):
        """Return calibration in the nested JSON schema expected by the loader."""
        return {
            "Info": self.comment,
            "Calibration coeff": {
                "Utpl": {
                    "0": float(self.utpl0),
                },
                "Ttpl": {
                    "0": float(self.ttpl0),
                    "1": float(self.ttpl1),
                },
                "Thtr": {
                    "0": float(self.thtr0),
                    "1": float(self.thtr1),
                    "2": float(self.thtr2),
                    "corr": float(self.thtrcorr),
                },
                "Thtrd": {
                    "0": float(self.thtrd0),
                    "1": float(self.thtrd1),
                    "2": float(self.thtrd2),
                    "corr": float(self.thtrdcorr),
                },
                "Uhtr": {
                    "0": float(self.uhtr0),
                    "1": float(self.uhtr1),
                },
                "Ihtr": {
                    "0": float(self.ihtr0),
                    "1": float(self.ihtr1),
                },
                "Theater": {
                    "0": float(self.theater0),
                    "1": float(self.theater1),
                    "2": float(self.theater2),
                },
                "Amplitude correction": {
                    "0": float(self.ac0),
                    "1": float(self.ac1),
                    "2": float(self.ac2),
                    "3": float(self.ac3),
                },
                "R heater": float(self.rhtr),
                "R guard": float(self.rghtr),
                "Heater safe voltage": float(self.safe_voltage),
            },
        }

    def read(self, path: str):
        """?????? ?????? `read`."""
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
        self.comment = self._json_calib.get(INFO_FIELD, self.comment)
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
        # [R heaters]
        self.rhtr = float(self._json_calib[CALIBRATION_COEFFS_FIELD][R_HEATER_FIELD])
        self.rghtr = float(self._json_calib[CALIBRATION_COEFFS_FIELD][R_GUARD_FIELD])
        # [Heater safe voltage]
        self.safe_voltage = float(self._json_calib[CALIBRATION_COEFFS_FIELD][HEATER_SAFE_VOLTAGE_FIELD])
        
        self._add_params()
        delattr(self, '_json_calib')            # need in order to transfer calibration dict without it in tango pipe

    '''def write(self, path: str):
        # [Info]
        self._json_calib[INFO_FIELD] = self.comment
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
        # [R heaters]
        self._json_calib[CALIBRATION_COEFFS_FIELD][R_HEATER_FIELD] = self.rhtr
        self._json_calib[CALIBRATION_COEFFS_FIELD][R_GUARD_FIELD] = self.rghtr
        # [Heater safe voltage]
        self._json_calib[CALIBRATION_COEFFS_FIELD][HEATER_SAFE_VOLTAGE_FIELD] = self.safe_voltage

        with open(path, 'w') as f:
            json.dump(self._json_calib, f, indent='\t')'''

    def _add_params(self):
        # parameters that are not in calibration file but need to use later
        """???????? ?????? `add_params`."""
        self.max_temp = self.theater0 * self.safe_voltage + \
                        self.theater1 * (self.safe_voltage ** 2) + \
                        self.theater2 * (self.safe_voltage ** 3)  # TODO: move calculation to another function
        self.min_temp = 0.
    
    def get_str(self):
        """?????????? ?????? `get_str`."""
        calib_str = str(self.__dict__)
        calib_str = calib_str.replace("\'", "\"")               # need because json.loads does not recognie " ' "
        return calib_str
    
    def ttplconv(self, value: float) -> float:
            """Convert temperature from ttpl to Celsius."""
            return self.ttpl0 * value + self.ttpl1 * (value ** 2)
    def thtrconv(self, value: float) -> float:
            """Convert temperature from thtr to Celsius."""
            return self.thtr0 + self.thtr1 * (value + self.thtrcorr) + \
                self.thtr2 * ((value + self.thtrcorr) ** 2)
    def thtrdconv(self, value: float) -> float:
            """Convert temperature from thtrd to Celsius."""
            return self.thtrd0 + self.thtrd1 * (value + self.thtrdcorr) + \
                self.thtrd2 * ((value + self.thtrdcorr) ** 2)
    def uhtrconv(self, value: float) -> float:
            """Convert voltage from uhtr to mV."""
            return (value + self.uhtr0) * self.uhtr1
    def ihtrconv(self, value: float) -> float:
            """Convert current from ihtr to mA."""
            return self.ihtr0 + self.ihtr1 * value
    def theaterconv(self, value: float) -> float:
            """Convert voltage from theater to Celsius."""
            return self.theater0 * value + self.theater1 * (value ** 2) + \
                self.theater2 * (value ** 3)
    def acconv(self, value: float) -> float:
        """Convert amplitude correction from ac to mV."""
        return self.ac0 + self.ac1 * value + self.ac2 * (value ** 2) + \
               self.ac3 * (value ** 3)      



    def apply_fh_cal(self, raw_data):
        """????????? ?????? `apply_fh_cal`."""
        import numpy as np
        data = pd.DataFrame(raw_data)
        values = data
        values[0]/=1
        values[1]/=1
        values[2]/=1
        values[3]/=1
        values[4]/=1
        values[5]/=1

        '''import numpy as np

        data = np.array(raw_data)

        Uref = data[:, 0]
        Umod = data[:, 1]
        #Uhtr = data[:, 2]
        Uaux = data[:, 3]
        Utpl = data[:, 4]
        Uhtr = data[:, 5]


        
        ################################
        # Taux
        ################################
        Uaux1=Uaux.mean()
        Taux = 100.0 * Uaux

        mask = Taux < -12.0
        if np.any(mask):
            Taux[mask] = (
                2.6843
                + 1.2709 * Taux[mask]
                + 0.0042867 * Taux[mask]**2
                + 3.4944e-05 * Taux[mask]**3
            )
        

        ################################
        # Thermopile temperature
        ################################
        Utpl_mV = Utpl * (1000.0 / 11.0)

        ax = Utpl_mV + self.utpl0
        temp = self.ttpl0 * ax + self.ttpl1 * (ax ** 2)
        temp = temp + Taux

        ################################
        # High-res temp
        ################################
        Umod_mV = Umod * (1000.0 / 121.0)

        ax = Umod_mV + self.utpl0
        temp_hr = self.ttpl0 * ax + self.ttpl1 * (ax ** 2)

        # ===============================
        # CURRENT
        # ===============================
        Ih = self.ihtr0 + Uref * self.ihtr1

        # ===============================
        # VOLTAGE → mV
        # ===============================
        Uhtr_mV = Uhtr * 1000.0
        Uref_mV = Uref * 1000.0

        # ===============================
        # RESISTANCE
        # ===============================
        Rhtr = np.zeros_like(Uhtr_mV)

        mask = Ih != 0

        Rhtr[mask] = (
            (Uhtr_mV[mask] - Uref_mV[mask] + self.uhtr0)
            * self.uhtr1
            / Ih[mask]
        )

        # ===============================
        # TEMPERATURE
        # ===============================
        Thtr = (
            self.thtr0
            + self.thtr1 * (Rhtr + self.thtrcorr)
            + self.thtr2 * (Rhtr + self.thtrcorr) ** 2
        )
        


        ################################
        # Heater temp
        ################################
        Thtrd = (
            self.thtr0
            + self.thtr1 * (Rhtr + self.thtrdcorr)
            + self.thtr2 * ((Rhtr + self.thtrdcorr) ** 2)
        )'''


        # Taux - mean for the whole buffer
        Uaux = values[3].mean()
        Taux = 100. * Uaux
        if Taux < -12.:  # correction for AD595 below -12 C
            Taux = 2.6843 + 1.2709 * Taux + 0.0042867 * Taux * Taux + 3.4944e-05 * Taux * Taux * Taux
        Taux = Taux
        Taux_arr = np.full(len(values), Taux)

        # Utpl or temp - temperature of the calibrated internal thermopile + Taux
        values[4] *= (1000. / 11.)  # scaling to mV with the respect of amplification factor of 11
        ax = values[4] + self.utpl0
        temp = self.ttpl0 * ax + self.ttpl1 * (ax ** 2)
        temp += Taux

        # temp-hr ??? add explanation Umod mV
        values[1] *= (1000. / 121.)  # scaling to mV; why 121?? amplifier cascade??
        ax = values[1] + self.utpl0
        temp_hr = self.ttpl0 * ax + self.ttpl1 * (ax ** 2)



        # Thtr
        values[5] *= 1000.  # ← включи если данные в В

        Ih = self.ihtr0 + values[0] * self.ihtr1

        eps = 1e-6
        mask = np.abs(Ih) > eps

        Rhtr = pd.Series(np.zeros(len(Ih)))

        Rhtr.loc[mask] = (
            (values[5].loc[mask] - values[0].loc[mask] * 1000. + self.uhtr0)
            * self.uhtr1
            / Ih.loc[mask]
        )

        Rhtr.loc[~mask] = np.nan

        Thtr = (
            self.thtr0
            + self.thtr1 * (Rhtr + self.thtrcorr)
            + self.thtr2 * ((Rhtr + self.thtrcorr) ** 2)
        )

       

        ################################
        # Output
        ################################
        calibrated = np.column_stack((
            temp,
            temp_hr,
            Ih.to_numpy(),
            Thtr.to_numpy(),
            Taux_arr
        ))
        return calibrated



      

    def unpack_data_numpy(raw_data, calibration):
        """
        raw_data: shape (N, 6)
        channels:
            0 - Uref
            1 - Umod
            2 - Uhtr
            3 - Uaux
            4 - Utpl
            5 - Uhtrabs (или raw Uhtr)
        """

        data = np.array(raw_data)

        Uref = data[:, 0]
        Umod = data[:, 1]
        Uhtr = data[:, 2]
        Uaux = data[:, 3]
        Utpl = data[:, 4]
        Uhtr_raw = data[:, 5]

        ########################################
        # SCALE (как в C++)
        ########################################

        Umod = Umod / 121.0 * 1000.0
        Utpl = Utpl / 11.0 * 1000.0
        Uhtr = Uhtr * 1000.0

        ########################################
        # Taux
        ########################################

        Taux = Uaux * 100.0

        mask = Taux < -12
        if np.any(mask):
            Taux[mask] = (
                2.6843
                + 1.2709 * Taux[mask]
                + 0.0042867 * Taux[mask]**2
                + 3.4944e-05 * Taux[mask]**3
            )

        ########################################
        # Ihtr
        ########################################

        Ihtr = calibration.ihtr0 + Uref * calibration.ihtr1

        ########################################
        # Uabs (важный кусок из C++)
        ########################################

        Uabs = Uhtr_raw - Uref * 1000.0
        Uabs = np.maximum(Uabs, 0)

        ########################################
        # Средние значения
        ########################################

        Ihtr_mean = np.mean(Ihtr)
        Utpl_mean = np.mean(Utpl)
        Uaux_mean = np.mean(Uaux)
        Uabs_mean = np.mean(Uabs)

        ########################################
        # Температура термопары
        ########################################

        ax = Utpl + calibration.utpl0
        Ttpl = calibration.ttpl0 * ax + calibration.ttpl1 * ax**2
        Ttpl_mean = np.mean(Ttpl)

        ########################################
        # Сопротивление нагревателя
        ########################################

        Rhtr = np.zeros_like(Uhtr)

        mask = Ihtr != 0
        Rhtr[mask] = Uabs[mask] / Ihtr[mask]

        ########################################
        # Температура нагревателя
        ########################################

        Thtr = (
            calibration.thtr0
            + calibration.thtr1 * (Rhtr + calibration.thtrcorr)
            + calibration.thtr2 * (Rhtr + calibration.thtrcorr) ** 2
        )

        ########################################
        # Мощность
        ########################################

        power = Uhtr * Ihtr

        ########################################
        # RMS (как в C++)
        ########################################

        valid = Ihtr > 0

        if np.any(valid):
            acurms = np.sqrt(np.mean((Uabs[valid] - np.mean(Uabs)) ** 2))
            acirms = np.sqrt(np.mean((Ihtr[valid] - np.mean(Ihtr)) ** 2))
        else:
            acurms = 0
            acirms = 0

        ########################################
        # Dynamic resistance
        ########################################

        Rhtrd = acurms / acirms if acirms > 0 else 0

        ########################################
        # Dynamic temperature
        ########################################

        Thtrd = (
            calibration.thtrd0
            + calibration.thtrd1 * (Rhtrd + calibration.thtrdcorr)
            + calibration.thtrd2 * (Rhtrd + calibration.thtrdcorr) ** 2
        )

        ########################################
        # ERROR (главная метрика)
        ########################################

        terror = Thtr - (Ttpl + Taux)

        ########################################
        # OUTPUT
        ########################################

        return {
            "Ihtr": Ihtr,
            "Rhtr": Rhtr,
            "Thtr": Thtr,
            "Thtrd": Thtrd,
            "Ttpl": Ttpl,
            "Taux": Taux,
            "Power": power,
            "Uabs": Uabs,
            "terror": terror,
            "Ihtr_mean": Ihtr_mean,
            "Ttpl_mean": Ttpl_mean,
            "Rhtrd": Rhtrd
        }
        # =========================================
        # SAVE DEBUG CSV
        # =========================================
        
        import os
        from datetime import datetime

        # 👉 сохраним raw ДО изменений (если не сделал раньше — лучше вынести выше)
        Uref_raw = data[0].copy()
        Uhtr_raw = data[5].copy()

        # 👉 пересчитаем mV нормально (чтобы видеть)
        Uref_mV = Uref_raw * 1000.0
        Uhtr_mV = Uhtr_raw * 1000.0

        # 👉 собираем всё в DataFrame
        df = pd.DataFrame({
            "0": data[0],
            "1": data[1],
            "3": data[3],
            "4": data[4],
            "5": data[5],
            
            "temp": temp,
            "temp_hr": temp_hr,
            "Ihtr": Ih,
            "Rhtr": Rhtr,
            "Thtr": Thtr,
            "Taux": Taux_arr,

            "Uref_raw": Uref_raw,
            "Uhtr_raw": Uhtr_raw,
            "Uref_mV": Uref_mV,
            "Uhtr_mV": Uhtr_mV,

            "Umod": data[1],
            "Uaux": data[3],
            "Utpl": data[4],
        })

        # 👉 путь
        folder = "debug_csv"
        os.makedirs(folder, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(folder, f"fh_debug_{ts}.csv")

        # 👉 ВАЖНО: нужные разделители
        df.to_csv(
            path,
            sep="\t",       # табуляция
            index=False,
            decimal=",",    # запятая как десятичный
            float_format="%.6f"
        )

        print(f"DEBUG CSV saved: {path}")
        return calibrated



if __name__ == '__main__':
    try:
        calib = Calibration()
        calib.read('//home//nanocal//PIONER_NEW//pioner//default_calibration.json')
        print(calib.get_str())

        print(calib.max_temp)
        calib.read('//home//nanocal//PIONER_NEW//pioner//default_calibration.json')
        print(calib.max_temp)

    except BaseException as e:
        print(e)
