from constants import JSON_EXTENSION
import json
import os

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
        # [Ttpl] = ttpl0*[Utpl] + ttpl1*[Utpl^2]                 
        self.ttpl0 = 1.                 
        self.ttpl1 = 0.
        # [Thtr] = thtr0 + thtr1*[R+thtrcorr] + thtr2*[(R+thtrcorr)^2]
        self.thtr0 = 0.
        self.thtr1 = 1.
        self.thtr2 = 0.
        self.thtrcorr = 48.94
        # [Thtrd] = thtrd0 + thtrd1*[R+thtrdcorr] + thtrd2*[(R+thtrdcorr)^2]
        self.thtrd0 = 0.
        self.thtrd1 = 1.
        self.thtrd2 = 0.
        self.thtrdcorr = 61.28 
        # [Uhtr] = ([U(mv)] + uhtr0)*uhtr1
        self.uhtr0 = 0.
        self.uhtr1 = 1.
        # [Ihtr] = ihtr0 + ihtr1*[I]
        self.ihtr0 = 0.
        self.ihtr1 = 1.
        # [Theater] = theater0*[U] + theater1*[U^2] + theater2*[U^3]
        self.theater0 = 2.
        self.theater1 = 0.
        self.theater2 = 0.
        # [Amplitude correction] = ac0 + ac1*[T] + ac2*[T^2] + ac3*[T^3]
        self.ac0 = 0.
        self.ac1 = 1.
        self.ac2 = 0.
        self.ac3 = 0.
        # [R heater]
        self.rhtr = 1700.
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
        self.comment = self._json_calib['Info']
    # [Modulation params]
        self.amplitude = float(self._json_calib['Modulation params']['Amplitude'])
        self.offset = float(self._json_calib['Modulation params']['Offset'])
        self.frequency = float(self._json_calib['Modulation params']['Frequency'])
    # [Gains]
        self.urefgain = float(self._json_calib['Gains']['Urefgain'])
        self.umodgain = float(self._json_calib['Gains']['Umodgain'])
        self.utplgain = float(self._json_calib['Gains']['Utplgain'])
        self.uhtrgain = float(self._json_calib['Gains']['Uhtrgain'])
    # [Calibration coeff]
        # [Utpl] = [U(mv)] + utpl0
        self.utpl0 = float(self._json_calib['Calibration coeff']['Utpl']['0'])
        # [Ttpl] = ttpl0*[Utpl] + ttpl1*[Utpl^2]                  
        self.ttpl0 = float(self._json_calib['Calibration coeff']['Ttpl']['0'])             
        self.ttpl1 = float(self._json_calib['Calibration coeff']['Ttpl']['1'])
        # [Thtr] = thtr0 + thtr1*[R+thtrcorr] + thtr2*[(R+thtrcorr)^2]
        self.thtr0 = float(self._json_calib['Calibration coeff']['Thtr']['0']) 
        self.thtr1 = float(self._json_calib['Calibration coeff']['Thtr']['1']) 
        self.thtr2 = float(self._json_calib['Calibration coeff']['Thtr']['2']) 
        self.thtrcorr = float(self._json_calib['Calibration coeff']['Thtr']['corr']) 
        # [Thtrd] = thtrd0 + thtrd1*[R+thtrdcorr] + thtrd2*[(R+thtrdcorr)^2]
        self.thtrd0 = float(self._json_calib['Calibration coeff']['Thtrd']['0']) 
        self.thtrd1 = float(self._json_calib['Calibration coeff']['Thtrd']['1']) 
        self.thtrd2 = float(self._json_calib['Calibration coeff']['Thtrd']['2']) 
        self.thtrdcorr = float(self._json_calib['Calibration coeff']['Thtrd'] ['corr']) 
        # [Uhtr] = ([U(mv)] + uhtr0)*uhtr1
        self.uhtr0 = float(self._json_calib['Calibration coeff']['Uhtr']['0']) 
        self.uhtr1 = float(self._json_calib['Calibration coeff']['Uhtr']['1']) 
        # [Ihtr] = ihtr0 + ihtr1*[I]
        self.ihtr0 = float(self._json_calib['Calibration coeff']['Ihtr']['0']) 
        self.ihtr1 = float(self._json_calib['Calibration coeff']['Ihtr']['1']) 
        # [Theater] = theater0*[U] + theater1*[U^2] + theater2*[U^3]
        self.theater0 = float(self._json_calib['Calibration coeff']['Theater']['0']) 
        self.theater1 = float(self._json_calib['Calibration coeff']['Theater']['1']) 
        self.theater2 = float(self._json_calib['Calibration coeff']['Theater']['2']) 
        # [Amplitude correction] = ac0 + ac1*[T] + ac2*[T^2] + ac3*[T^3]
        self.ac0 = float(self._json_calib['Calibration coeff']['Amplitude correction']['0']) 
        self.ac1 = float(self._json_calib['Calibration coeff']['Amplitude correction']['1']) 
        self.ac2 = float(self._json_calib['Calibration coeff']['Amplitude correction']['2']) 
        self.ac3 = float(self._json_calib['Calibration coeff']['Amplitude correction']['3']) 
        # [R heater]
        self.rhtr = float(self._json_calib['Calibration coeff']['R heater'])
        # [Heater safe voltage]
        self.safe_voltage = float(self._json_calib['Calibration coeff']['Heater safe voltage'])
        
        self._add_params()

    def write(self, path: str):
        # [Info]
        self._json_calib['Info'] = self.comment
    # [Modulation params]
        self._json_calib['Modulation params']['Amplitude'] = self.amplitude
        self._json_calib['Modulation params']['Offset'] = self.offset
        self._json_calib['Modulation params']['Frequency'] = self.frequency
    # [Gains]
        self._json_calib['Gains']['Urefgain'] = self.urefgain
        self._json_calib['Gains']['Umodgain'] = self.umodgain
        self._json_calib['Gains']['Utplgain'] = self.utplgain
        self._json_calib['Gains']['Uhtrgain'] = self.uhtrgain
    # [Calibration coeff]
        # [Utpl] = [U(mv)] + utpl0
        self._json_calib['Calibration coeff']['Utpl']['0'] = self.utpl0
        # [Ttpl] = ttpl0*[Utpl] + ttpl1*[Utpl^2]               
        self._json_calib['Calibration coeff']['Ttpl']['0'] = self.ttpl0            
        self._json_calib['Calibration coeff']['Ttpl']['1'] = self.ttpl1
        # [Thtr] = thtr0 + thtr1*[R+thtrcorr] + thtr2*[(R+thtrcorr)^2]
        self._json_calib['Calibration coeff']['Thtr']['0'] = self.thtr0
        self._json_calib['Calibration coeff']['Thtr']['1'] = self.thtr1 
        self._json_calib['Calibration coeff']['Thtr']['2'] = self.thtr2
        self._json_calib['Calibration coeff']['Thtr']['corr'] = self.thtrcorr 
        # [Thtrd] = thtrd0 + thtrd1*[R+thtrdcorr] + thtrd2*[(R+thtrdcorr)^2]
        self._json_calib['Calibration coeff']['Thtrd']['0'] = self.thtrd0 
        self._json_calib['Calibration coeff']['Thtrd']['1'] = self.thtrd1 
        self._json_calib['Calibration coeff']['Thtrd']['2'] = self.thtrd2 
        self._json_calib['Calibration coeff']['Thtrd'] ['corr'] = self.thtrdcorr 
        # [Uhtr] = ([U(mv)] + uhtr0)*uhtr1
        self._json_calib['Calibration coeff']['Uhtr']['0'] = self.uhtr0
        self._json_calib['Calibration coeff']['Uhtr']['1'] = self.uhtr1
        # [Ihtr] = ihtr0 + ihtr1*[I]
        self._json_calib['Calibration coeff']['Ihtr']['0'] = self.ihtr0
        self._json_calib['Calibration coeff']['Ihtr']['1'] = self.ihtr1
        # [Theater] = theater0*[U] + theater1*[U^2] + theater2*[U^3]
        self._json_calib['Calibration coeff']['Theater']['0'] = self.theater0
        self._json_calib['Calibration coeff']['Theater']['1'] = self.theater1
        self._json_calib['Calibration coeff']['Theater']['2'] = self.theater2
        # [Amplitude correction] = ac0 + ac1*[T] + ac2*[T^2] + ac3*[T^3]
        self._json_calib['Calibration coeff']['Amplitude correction']['0'] = self.ac0
        self._json_calib['Calibration coeff']['Amplitude correction']['1'] = self.ac1
        self._json_calib['Calibration coeff']['Amplitude correction']['2'] = self.ac2 
        self._json_calib['Calibration coeff']['Amplitude correction']['3'] = self.ac3
        # [R heater]
        self._json_calib['Calibration coeff']['R heater'] = self.rhtr
        # [Heater safe voltage]
        self._json_calib['Calibration coeff']['Heater safe voltage'] = self.safe_voltage

        with open(path, 'w') as f:
            json.dump(self._json_calib, f, indent='\t')

    def _add_params(self):
        # parameters that are not in calibration file but need to use later
        self.maxtemp = self.theater0 * self.safe_voltage + \
                       self.theater1 * (self.safe_voltage ** 2) + \
                       self.theater2 * (self.safe_voltage ** 3)
        self.mintemp = 0.


if __name__ == '__main__':
    try:
        calib = Calibration()
        print(calib.maxtemp)
        calib.read('./calibration.json')
        print(calib.maxtemp)
    except BaseException as e:
        print(e)