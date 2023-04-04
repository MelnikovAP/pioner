from silx.gui import qt
from silx.gui.plot import Plot1D

from mainWindowUi import mainWindowUi
from messageWindows import *
from configWindow import *
from calibWindow import *
from settings import *
from constants import *

import requests
import pandas as pd
import numpy as np
import json
import os
import h5py


class mainWindow(mainWindowUi):
    def __init__(self, parent=None):
        super(mainWindow, self).__init__(parent)

        self.device = None          # patch for disconnect method. to be changed later
        self.preload_settings()

        self.sysOnButton.clicked.connect(self.sysOnButtonPressed)
        self.sysOffButton.clicked.connect(self.disconnect)
        self.sysDataPathButton.clicked.connect(self.select_data_path)
        self.sysSetupButton.clicked.connect(self.show_help)

        self.calibPathButton.clicked.connect(self.select_calibration_file)
        self.calibViewButton.clicked.connect(self.view_calibraton_info)
        self.calibApplyButton.clicked.connect(self.apply_calib)

        self.applyScanSampleRateButton.clicked.connect(self.apply_sample_rate)
        self.resetScanSampleRateButton.clicked.connect(self.reset_sample_rate)

        self.armButton.clicked.connect(self.fh_arm)
        self.startButton.clicked.connect(self.fh_run)

        self.setTempVoltButton.clicked.connect(self.set_temp_volt)
        self.unsetTempVoltButton.clicked.connect(self.unset_temp_volt)

# for debugging
        self.terror0Button.clicked.connect(self.print_debug)

    def print_debug(self):
        print(self.settings.sample_rate)
        print(self.calibration.comment)
# end for debugging
    
    def sysOnButtonPressed(self):
        self.set_connection()
        # TODO: add continious aquisition after modulation starts to check signals

    def set_connection(self):
        
        if self.sysNoHardware.isChecked() != True:
            # AM: cannot install TANGO on MAC OS. so I've added importing tango here
            # in order to include feature with no-hardware mode 
            try:
                import tango

                self.device = tango.DeviceProxy(self.settings.device_proxy)
                self.device.set_timeout_millis(10000000)
                self.device.set_connection()
            
                if self.settings.calib_path == 'default calibration':
                    self.apply_default_calib()
                else: 
                    self.apply_calib()
                [item.setEnabled(True) for item in [self.experimentBox, self.controlTab]]

                self.device.set_sample_scan_rate(self.settings.sample_rate)

            except:
                ## No-hardware mode for data processing
                error_text = "No connection to the device or\nTANGO module not found!\nOnly no-hardware mode is possible."
                ErrorWindow(error_text)
                self.run_no_harware()
        else:
            self.run_no_harware()


    
    def disconnect(self):
        if self.device:
           self.device.disconnect()
        [item.setEnabled(False) for item in [self.experimentBox, self.controlTab]]
        self.sysNoHardware.setEnabled(True)
    
    def select_data_path(self):
        dpath = qt.QFileDialog.getExistingDirectory(self, "Choose folder to save experiment files", \
                                                    None, qt.QFileDialog.ShowDirsOnly)
        if dpath: 
            self.sysDataPathInput.setText(os.path.abspath(dpath))
            self.settings.data_path = dpath
            print(self.sysDataPathInput.text())
        self.sysDataPathInput.setCursorPosition(0)

    def show_help(self):
        self.configWindow = configWindow(parent=self)
        self.configWindow.show()

    def run_no_harware(self):
        self.sysNoHardware.setChecked(True)
        self.controlTabsWidget.setCurrentIndex(1) 
        self.mainTabWidget.setCurrentIndex(1) 
    # ===================================
    # Calibration   

    def select_calibration_file(self):
        fname = qt.QFileDialog.getOpenFileName(self, "Choose calibration file", None, "*.json")[0]
        if fname: 
            self.calibPathInput.setText(os.path.abspath(fname))
            self.settings.calib_path = fname
        self.calibPathInput.setCursorPosition(0)

    def apply_calib(self):
        fpath = self.calibPathInput.text()
        if os.path.exists(os.path.abspath(fpath)):
            with open(self.calibPathInput.text(), 'r') as f:
                raw_calib = json.load(f)
                str_calib = json.dumps(raw_calib)
                self.device.load_calibration(str_calib)
                self.device.apply_calibration()
                self.get_calib_from_device()

    def apply_default_calib(self):
        self.device.apply_default_calibration()
        self.get_calib_from_device()
        self.calibPathInput.setText('default calibration')

    def get_calib_from_device(self):
        calib_str = self.device.get_current_calibration[1][0]['value']
        calib_dict = json.loads(calib_str)
        self.calibration = Dict2Class(calib_dict)

    def view_calibraton_info(self):
        self.calibWindow = calibWindow(parent=self)
        self.calibWindow.show()
    
    # ===================================
    # Settings
    def preload_settings(self):
        self.load_settings_from_file()
        if not self.settings: 
            quit()

        if not os.path.exists(self.settings.data_path):
            error_text = "Incorrect data path specified.\nIt will be set to ./data/"
            ErrorWindow(error_text)
            if not os.path.exists('./data/'):
                os.makedirs('./data/')
            self.settings.data_path = os.path.abspath('./data/')
        self.sysDataPathInput.setText(os.path.abspath(self.settings.data_path))
        self.sysDataPathInput.setCursorPosition(0)

        if os.path.exists(self.settings.calib_path):
            self.calibPathInput.setText(os.path.abspath(self.settings.calib_path))
            self.calibPathInput.setCursorPosition(0)
        else:
            error_text = "Incorrect calibration file specified.\nIt will be set to default calibration."
            ErrorWindow(error_text)
            self.calibPathInput.setText('default calibration')
            self.settings.calib_path = 'default calibration'   

        self.scanSampleRateInput.setText(str(self.settings.sample_rate))

        self.freqInput.setText(str(self.settings.modulation_frequency))
        self.amplitudeInput.setText(str(self.settings.modulation_amplitude))
        self.offsetInput.setText(str(self.settings.modulation_offset))  

    def apply_sample_rate(self):
        self.settings.sample_rate = int(self.scanSampleRateInput.text())
        self.device.set_sample_scan_rate(self.settings.sample_rate)
    
    def reset_sample_rate(self):
        self.device.reset_sample_scan_rate()
        self.settings.sample_rate = self.get_sample_rate_from_device()
        self.scanSampleRateInput.setText(str(self.settings.sample_rate))

    def get_sample_rate_from_device(self):    
        return self.device.get_sample_rate[1][0]['value']


    # ===================================
    # Fast heating

    def fh_arm(self):
        xOption = 1000 if self.experimentTimeComboBox.currentIndex()==1 else 1    #0 - time in ms, 1 - time in s
        yOption = self.experimentTempComboBox.currentIndex() #index 0 - temp in C, 1 - volt in V
        uncorrectedProfile = np.array([[],[]], dtype=float)
        for i in range(self.experimentTable.rowCount()):
            uncorrectedProfile = np.hstack((uncorrectedProfile,
                                            [[float(self.experimentTable.item(i, 0).text())],
                                            [float(self.experimentTable.item(i, 1).text())]]))
        correctedProfile = uncorrectedProfile[:, :(np.argmax(uncorrectedProfile[0])+1)]
        correctedProfile = np.insert(correctedProfile, 0, 0, axis=1)
        self.time_table = xOption*correctedProfile[0] # changing s to ms if needed
        self.temp_table = correctedProfile[1]
        
        self.progressBar.setValue(0)  
        self.controlTabsWidget.setCurrentIndex(1) 
        self.progPlot.resultPlot.clear()
        
        y_label = self.experimentTempComboBox.currentText()
        x_label = self.experimentTimeComboBox.currentText()
        self.progPlot.resultPlot.addCurve(x=self.time_table, y=self.temp_table, 
                                            legend="temperature", 
                                            color=self.progPlot.curveColors['red'])
        self.progPlot.resultPlot.getXAxis().setLabel(x_label)
        self.progPlot.resultPlot.getYAxis().setLabel(y_label)

        # generating time_temp_volt_tables as dict, converting it to str
        # to pass to run_fast_heat (tango)
        self.time_temp_volt_tables = {'ch0':{}, 'ch1':{}, 'ch2':{}}

        # 0.1V on 0 channel
        self.time_temp_volt_tables['ch0']['time'] = self.time_table.tolist()
        self.time_temp_volt_tables['ch0']['volt'] = [0.1]*len(self.time_table) 

        # signal to heater - channel 1
        self.time_temp_volt_tables['ch1']['time'] = self.time_table.tolist()
        self.time_temp_volt_tables['ch1']['temp'] = self.temp_table.tolist()

        # 2.5V trigger signal like gate form
        self.time_temp_volt_tables['ch2']['time'] =  self.time_table.tolist()
        self.time_temp_volt_tables['ch2']['time'].insert(-1, self.time_temp_volt_tables['ch2']['time'][-1]-1)
        self.time_temp_volt_tables['ch2']['volt'] = [2.5]*(len(self.time_table)+1)
        self.time_temp_volt_tables['ch2']['volt'][-1] = 0

        self.time_temp_volt_tables_str = json.dumps(self.time_temp_volt_tables)
        self.device.arm_fast_heat(self.time_temp_volt_tables_str)

    def _fh_download_raw_data(self):
        URL = self.settings.http_host+"data/raw_data/raw_data.h5"
        response = requests.get(URL, verify=False)
        with open('./data/raw_data.h5', 'wb') as f:
            f.write(response.content)
    
    def _fh_download_exp_data(self):
        URL = self.settings.http_host+"data/exp_data.h5"
        response = requests.get(URL, verify=False)
        fname = qt.QFileDialog.getSaveFileName(self, "Save data to file", 
                                                self.settings.data_path+'exp_data.h5', 
                                                "*.h5")[0]
        if fname:
            with open(fname, 'wb') as f:
                f.write(response.content)
        self.currentExpFilePath = fname

    def _fh_transform_exp_data(self):
        self.exp_data = pd.DataFrame({})
        if self.currentExpFilePath:
            with h5py.File(self.currentExpFilePath, 'r') as f:
                data = f['data']
                for key in list(data.keys()):
                    self.exp_data[key] = data[key][:]

    def _fh_plot_data(self):
        self.resultsDataWidget.clear()
        if not self.exp_data.empty:
            _keys = list(self.exp_data.keys())
            _keys.remove('time')
            for idx, key in enumerate(_keys):
                color = self.resultsDataWidget.curveColors[list(self.resultsDataWidget.curveColors.keys())[idx]]
                self.resultsDataWidget.addCurve(self.exp_data['time'], 
                                                self.exp_data[key], 
                                                legend = key,
                                                color=color)
            for curve in self.resultsDataWidget.resultPlot.getItems():
                if curve.getName()!="temp":
                    curve.setVisible(False)
            self.mainTabWidget.setCurrentIndex(1) 
        self.resultsDataWidget.resultPlot.resetZoom()
        

    def fh_run(self):
        self.device.run_fast_heat()
        self._fh_download_raw_data()
        self._fh_download_exp_data()
        self._fh_transform_exp_data()
        self._fh_plot_data()

    # ===================================
    # Iso (set) mode
    def set_temp_volt(self):
        value = float(self.setInput.text())
        print(value)
        key = str(self.setComboBox.currentText())
        if key=="Temperature":
            key="temp"
        if key=="Voltage":
            key="volt"
        print(key)
        chan_temp_volt = {"ch2": {key:value} }
        
        self.chan_temp_volt_str = json.dumps(chan_temp_volt)
        self.device.arm_iso_mode(self.chan_temp_volt_str)
        self.device.run_iso_mode()
    
    def unset_temp_volt(self):
        chan_temp_volt = {"ch1": {"volt":0} }
        self.chan_temp_volt_str = json.dumps(chan_temp_volt)
        self.device.arm_iso_mode(self.chan_temp_volt_str)
        self.device.run_iso_mode()



    # ===================================
    def save_settings_to_file(self, fpath=False):
        # function is used to save settings to default file or to special file if specified
        if not fpath:
            fpath = os.path.abspath(SETTINGS_FILE_REL_PATH)
        else:
            fpath = qt.QFileDialog.getSaveFileName(self, "Select file and path to save settings:", None, "*.json")[0]
        if fpath:
            with open(fpath, 'w') as f:
                json.dump(self.settings.get_dict(), f, separators=(',', ': '), indent=4)

    def load_settings_from_file(self, fpath=False):
        # function is used to load default settings or to load special config from file if specified
        if not fpath:
            fpath = os.path.abspath(SETTINGS_FILE_REL_PATH)
        else:
            fpath = qt.QFileDialog.getOpenFileName(self, "Choose file with settings:", None, "*.json")[0]
        try:
            self.settings = Settings(fpath)
            self.disconnect()
        except:
            error_text = "Settings file is missing or corrupted! Settings will be reset to default."
            ErrorWindow(error_text)
            self.settings = mainParams()

    def reset_settings(self):
        # reset config params; used default attributes from Params class
        self.settings = mainParams()
        self.save_settings_to_file()
        self.disconnect()

    def closeEvent(self, event):
        # dumping current settings to ./settings/.settings.json and closing all the windows
        self.save_settings_to_file()
        for window in qt.QApplication.topLevelWidgets():
            window.close()



# Turns a dictionary into a class
class Dict2Class(object):
    def __init__(self, my_dict):
        for key in my_dict:
            setattr(self, key, my_dict[key])
        self.my_dict = my_dict
    def get_dict(self):
        return self.my_dict