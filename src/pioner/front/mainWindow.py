"""Main window of the PIONER GUI.

TODO(global): only the *fast* mode is wired up here. The Tango server now
exposes a ``select_mode`` command that takes ``"fast"``, ``"slow"``, or
``"iso"`` plus the unified ``arm(programs_json)`` / ``run`` pair. Add a UI
element (combo box) that drives ``select_mode`` and re-uses the existing
profile editor for slow-mode programs (DC ramp). The modulation block in
``settings.json`` (Frequency / Amplitude / Offset) is already plumbed via
``BackSettings.modulation`` and used by :class:`pioner.back.modes.SlowMode`.
"""

import json
import os
import shutil
from typing import Any

import h5py
import numpy as np
import pandas as pd
import requests
from silx.gui import qt

from pioner.front.calibWindow import *
from pioner.front.configWindow import *
from pioner.front.mainWindowUi import mainWindowUi
from pioner.front.messageWindows import *
from pioner.shared.channels import HEATER_AO
from pioner.shared.constants import *
from pioner.shared.settings import FrontSettings
from pioner.shared.utils import Dict2Class


def _relative_if_under_cwd(path: str) -> str:
    """Return ``path`` as a './'-prefixed relative path if it sits under cwd,
    otherwise the absolute form. Keeps settings.json portable across machines
    when paths point inside the project tree."""
    abs_path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())
    try:
        rel = os.path.relpath(abs_path, cwd)
    except ValueError:
        return abs_path
    if rel.startswith(".."):
        return abs_path
    return os.path.join(".", rel)


class mainWindow(mainWindowUi):
    def __init__(self, parent=None):
        super(mainWindow, self).__init__(parent)

        # Tango DeviceProxy when connected. Typed as ``Any`` (not Optional)
        # because PyTango exposes commands/attributes/pipes via __getattr__:
        # the static checker has no way of knowing them. Runtime ``None``
        # checks (``if self.device is None``) protect against unconnected
        # state at every call site that needs the wire.
        self.device: Any = None
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

        self.applyModulationParamsButton.clicked.connect(self.apply_modulation_params)
        self.resetModulationParamsButton.clicked.connect(self.reset_modulation_params)

        self.armButton.clicked.connect(self.fh_arm)
        self.startButton.clicked.connect(self.fh_run)

        self.setTempVoltButton.clicked.connect(self.set_temp_volt)
        self.unsetTempVoltButton.clicked.connect(self.unset_temp_volt)

# for debugging
        self.terror0Button.clicked.connect(self.print_debug)

    def print_debug(self):
        print(self.settings.sample_rate)
        calibration = getattr(self, "calibration", None)
        print(calibration.comment if calibration is not None else "no calibration loaded")
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
                print(self.settings.get_server_settings())
                self.device.set_connection()
                print('success')

                if self.settings.calib_path == DEFAULT_CALIBRATION_FILE_REL_PATH:
                    self.apply_default_calib()
                else: 
                    self.apply_calib()
                [item.setEnabled(True) for item in [self.experimentBox, self.controlTab]]

                self.device.set_sample_scan_rate(self.settings.sample_rate)

            except Exception:
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
            dpath += '/'
            # Prefer relative-to-cwd so settings.json stays portable across
            # checkouts; fall back to absolute when the choice is outside cwd.
            self.settings.data_path = _relative_if_under_cwd(dpath)
            self.sysDataPathInput.setText(self.settings.data_path)
        self.sysDataPathInput.setCursorPosition(0)

    def show_help(self):
        self.configWindow = configWindow(parent=self)
        self.configWindow.show()

    def run_no_harware(self):
        self.sysNoHardware.setChecked(True)
        # Keep experiment widgets interactive so the operator can explore the
        # program editor / plots without hardware. Tango calls in fh_arm,
        # set_temp_volt etc. guard against ``self.device is None``.
        for item in (self.experimentBox, self.controlTab):
            item.setEnabled(True)
        self.controlTabsWidget.setCurrentIndex(1)
        self.mainTabWidget.setCurrentIndex(1)
    # ===================================
    # Calibration   

    def select_calibration_file(self):
        fname = qt.QFileDialog.getOpenFileName(self, "Choose calibration file", None, "*.json")[0]
        if fname:
            self.settings.calib_path = _relative_if_under_cwd(fname)
            self.calibPathInput.setText(self.settings.calib_path)
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
        self.calibPathInput.setText(os.path.abspath(DEFAULT_CALIBRATION_FILE_REL_PATH))
        self.calibPathInput.setCursorPosition(0)

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
        if not os.path.exists(SETTINGS_FOLDER_REL_PATH):
            os.makedirs(SETTINGS_FOLDER_REL_PATH)
        if not os.path.exists(SETTINGS_FILE_REL_PATH):
            shutil.copy(DEFAULT_SETTINGS_FILE_REL_PATH, SETTINGS_FILE_REL_PATH)
        if not os.path.exists(DATA_FOLDER_REL_PATH):
            os.makedirs(DATA_FOLDER_REL_PATH)

        self.load_settings_from_file()
        if not getattr(self, "settings", None):
            raise SystemExit("Failed to load settings; cannot start UI.")

        if not os.path.exists(self.settings.data_path):
            error_text = "Incorrect data path specified.\nIt will be set to {}".format(DATA_FOLDER_REL_PATH)
            ErrorWindow(error_text)
            self.settings.data_path = _relative_if_under_cwd(DATA_FOLDER_REL_PATH)
        self.sysDataPathInput.setText(self.settings.data_path)
        self.sysDataPathInput.setCursorPosition(0)

        if not os.path.exists(self.settings.calib_path):
            error_text = "Incorrect calibration file specified.\nIt will be set to default calibration."
            ErrorWindow(error_text)
            self.settings.calib_path = _relative_if_under_cwd(DEFAULT_CALIBRATION_FILE_REL_PATH)
        self.calibPathInput.setText(self.settings.calib_path)
        self.calibPathInput.setCursorPosition(0)

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

    def apply_modulation_params(self):
        try:
            self.settings.modulation_frequency = float(self.freqInput.text())
            self.settings.modulation_amplitude = float(self.amplitudeInput.text())
            self.settings.modulation_offset = float(self.offsetInput.text())
        except ValueError:
            ErrorWindow("Modulation inputs must be numeric.")

    def reset_modulation_params(self):
        self.freqInput.setText(str(self.settings.modulation_frequency))
        self.amplitudeInput.setText(str(self.settings.modulation_amplitude))
        self.offsetInput.setText(str(self.settings.modulation_offset))


    # ===================================
    # Fast heating

    def fh_arm(self):
        xOption = 1000 if self.experimentTimeComboBox.currentIndex()==1 else 1    # 0 - time in ms, 1 - time in s
        # 0 - temp (°C), 1 - volt (V). Heater channel key depends on this.
        is_voltage_program = self.experimentTempComboBox.currentIndex() == 1
        heater_value_key = "volt" if is_voltage_program else "temp"
        uncorrectedProfile = np.array([[],[]], dtype=float)
        for i in range(self.experimentTable.rowCount()):
            # Cells are populated with QTableWidgetItem('0') in mainWindowUi
            # __init__, so item(i, c) is never None here.
            t_item = self.experimentTable.item(i, 0)
            v_item = self.experimentTable.item(i, 1)
            assert t_item is not None and v_item is not None
            uncorrectedProfile = np.hstack((uncorrectedProfile,
                                            [[float(t_item.text())],
                                            [float(v_item.text())]]))
        # Trim trailing zero-padded rows: keep up to the row with max time.
        # If every cell is zero the resulting profile would have duration 0,
        # which the backend (rightly) rejects -- fail loudly here instead of
        # sending a degenerate program over Tango.
        if not np.any(uncorrectedProfile[0] > 0):
            ErrorWindow("Program table is empty: enter at least one row with time > 0.")
            return
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

        # Signal to heater - channel 1 (use the unit selected by the user;
        # silently sending ``temp`` while the user picked ``Voltage`` would
        # send the value through the calibration polynomial, which is wrong).
        self.time_temp_volt_tables['ch1']['time'] = self.time_table.tolist()
        self.time_temp_volt_tables['ch1'][heater_value_key] = self.temp_table.tolist()

        # 2.5V trigger signal like gate form
        self.time_temp_volt_tables['ch2']['time'] =  self.time_table.tolist()
        self.time_temp_volt_tables['ch2']['time'].insert(-1, self.time_temp_volt_tables['ch2']['time'][-1]-1)
        self.time_temp_volt_tables['ch2']['volt'] = [2.5]*(len(self.time_table)+1)
        self.time_temp_volt_tables['ch2']['volt'][-1] = 0

        self.time_temp_volt_tables_str = json.dumps(self.time_temp_volt_tables)
        if self.device is None:
            return  # no-hardware mode: program plotted, but cannot be armed
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
                                                self.settings.data_path+'/exp_data.h5', 
                                                "*.h5")[0]
        if fname:
            with open(fname, 'wb') as f:
                f.write(response.content)
        self.currentExpFilePath = fname

    def _fh_transform_exp_data(self):
        self.exp_data = pd.DataFrame({})
        if self.currentExpFilePath:
            with h5py.File(self.currentExpFilePath, 'r') as f:
                # h5py['name'] returns Group|Dataset|Datatype; for our exp file
                # 'data' is always a Group, and each child is a Dataset.
                data = f['data']
                assert isinstance(data, h5py.Group)
                for key in list(data.keys()):
                    ds = data[key]
                    assert isinstance(ds, h5py.Dataset)
                    self.exp_data[key] = ds[:]

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
        if self.device is None:
            ErrorWindow("No hardware connection: cannot run experiment.")
            return
        self.device.run_fast_heat()
        self._fh_download_raw_data()
        self._fh_download_exp_data()
        self._fh_transform_exp_data()
        self._fh_plot_data()

    # ===================================
    # Iso (set) mode
    # The "Set" / "Off" pair must target the *same* AO channel so that "Off"
    # actually neutralises the previous "Set". The heater is wired on ch1 in
    # ``fh_arm`` above (and is the default ``modulation_channel`` in the
    # backend), so both endpoints write to ch1.
    HEATER_CHANNEL_KEY = HEATER_AO

    def set_temp_volt(self):
        if self.device is None:
            ErrorWindow("No hardware connection: cannot set iso value.")
            return
        try:
            value = float(self.setInput.text())
        except ValueError:
            ErrorWindow("Iso input must be numeric.")
            return
        key = "temp" if self.setComboBox.currentText() == "Temperature" else "volt"
        chan_temp_volt = {self.HEATER_CHANNEL_KEY: {key: value}}
        self.chan_temp_volt_str = json.dumps(chan_temp_volt)
        self.device.arm_iso_mode(self.chan_temp_volt_str)
        self.device.run_iso_mode()

    def unset_temp_volt(self):
        if self.device is None:
            return
        chan_temp_volt = {self.HEATER_CHANNEL_KEY: {"volt": 0}}
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
            with open(fpath, 'r') as f:
                file_settings = json.load(f)

            file_settings[SERVER_SETTINGS_FIELD] = self.settings.get_server_settings()
            file_settings[EXPERIMENT_SETTINGS_FIELD] = self.settings.get_exp_settings()

            with open(fpath, 'w') as f:
                json.dump(file_settings, f, separators=(',', ': '), indent=4)

    def load_settings_from_file(self, fpath=False):
        # function is used to load default settings or to load special config from file if specified
        if not fpath:
            fpath = os.path.abspath(SETTINGS_FILE_REL_PATH)
        else:
            fpath = qt.QFileDialog.getOpenFileName(self, "Choose file with settings:", None, "*.json")[0]
        try:
            self.settings = FrontSettings(fpath)
            self.disconnect()
        except Exception:
            error_text = "Settings file is missing or corrupted! Settings will be reset to default."
            ErrorWindow(error_text)
            self.reset_settings()

    def reset_settings(self):
        # reset config params; used default attributes from Params class
        self.settings = FrontSettings(DEFAULT_SETTINGS_FILE_REL_PATH)

    def closeEvent(self, event):
        # dumping current settings to ./settings/settings.json and closing all the windows
        self.save_settings_to_file()
        for window in qt.QApplication.topLevelWidgets():
            window.close()




