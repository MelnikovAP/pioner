from silx.gui import qt
import os
import json
import logging
from pathlib import Path
#from constants import *


from pioner_app.core.settings import *
from pioner_app.ui.localization import apply_language, tr



def _dialog_options():
    """???????? ?????? `dialog_options`."""
    options = qt.QFileDialog.Options()
    options |= qt.QFileDialog.DontUseNativeDialog
    return options


def _make_window_modal(widget):
    """???????? ?????? `make_window_modal`."""
    widget.setWindowModality(qt.Qt.WindowModal)
    widget.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)
    return widget


class calibWindow(qt.QDialog):
    def __init__(self, parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super(calibWindow, self).__init__(parent=parent)

        # ####### UI setup
        # ########################################
        short_line_input_width = 60

        self.setWindowTitle("Calibration info")
        self.resize(620, 760)
        self.setMinimumSize(520, 680)
        _make_window_modal(self)

        mainLayout = qt.QVBoxLayout()
        mainLayout.setAlignment(qt.Qt.AlignHCenter)
        self.setLayout(mainLayout)
        
        lout_1 = qt.QHBoxLayout()
        mainLayout.addLayout(lout_1)
        labl = qt.QLabel("Calibration info: ")
        labl.setMinimumWidth(75)
        lout_1.addWidget(labl)
        self.calibInfoInput = qt.QLineEdit()
        self.calibInfoInput.setFrame(False)
        lout_1.addWidget(self.calibInfoInput)

        lout_calib_files = qt.QHBoxLayout()
        mainLayout.addLayout(lout_calib_files)
        lout_calib_files.addWidget(qt.QLabel("Calibration file: "))
        self.calibrationFilesCombo = qt.QComboBox()
        self.calibrationFilesCombo.setMinimumWidth(240)
        lout_calib_files.addWidget(self.calibrationFilesCombo, 1)
        self.refreshCalibrationFilesButton = qt.QToolButton()
        self.refreshCalibrationFilesButton.setText("R")
        self.refreshCalibrationFilesButton.setToolTip("Refresh calibration file list")
        lout_calib_files.addWidget(self.refreshCalibrationFilesButton)

        self.liveValuesBox = qt.QGroupBox("Live values")
        mainLayout.addWidget(self.liveValuesBox)
        live_layout = qt.QGridLayout()
        self.liveValuesBox.setLayout(live_layout)
        self.live_value_labels = {}
        live_rows = [
            ("Utpl raw (mV)", "utpl_raw"),
            ("Ttpl (C)", "ttpl_cal"),
            ("Uhtr raw (mV)", "uhtr_raw"),
            ("Uhtr cal (mV)", "uhtr_cal"),
            ("Ihtr raw", "ihtr_raw"),
            ("Ihtr cal (mA)", "ihtr_cal"),
            ("Rhtr (Ohm)", "rhtr"),
            ("Thtr (C)", "thtr"),
            ("Rhtrd (Ohm)", "rhtrd"),
            ("Thtrd (C)", "thtrd"),
        ]
        for row, (label_text, key) in enumerate(live_rows):
            live_layout.addWidget(qt.QLabel(label_text), row, 0)
            value_label = qt.QLabel("---")
            value_label.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
            live_layout.addWidget(value_label, row, 1)
            self.live_value_labels[key] = value_label

        self.ttplBox = qt.QGroupBox("Thermopile temperature")
        mainLayout.addWidget(self.ttplBox)
        lout_0 = qt.QVBoxLayout()
        self.ttplBox.setLayout(lout_0)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        self.ttplBoxLabl1 = qt.QLabel("000.000")
        self.ttplBoxLabl2 = qt.QLabel("000.000")
        self.ttplBoxInput1 = qt.QLineEdit()
        self.ttplBoxInput1.setMaximumWidth(short_line_input_width)
        self.ttplBoxInput1.setFrame(False)
        self.ttplBoxResetButton = qt.QPushButton("->0")
        self.ttplBoxResetButton.setFixedWidth(25)
        self.ttplBoxResetButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.setSpacing(0)
        lout_1.addWidget(qt.QLabel("Utpl, mV : "))
        lout_1.addWidget(self.ttplBoxLabl1)
        lout_1.addWidget(qt.QLabel(" = "))
        lout_1.addWidget(self.ttplBoxLabl2)
        lout_1.addWidget(qt.QLabel(" + "))
        lout_1.addWidget(self.ttplBoxInput1)
        lout_1.addStretch()
        lout_1.addWidget(self.ttplBoxResetButton)
        lout_2 = qt.QHBoxLayout()
        lout_0.addLayout(lout_2)
        self.ttplBoxLabl2 = qt.QLabel("000.000")
        self.ttplBoxInput2 = qt.QLineEdit()
        self.ttplBoxInput2.setMaximumWidth(short_line_input_width)
        self.ttplBoxInput2.setFrame(False)
        self.ttplBoxInput3 = qt.QLineEdit()
        self.ttplBoxInput3.setMaximumWidth(short_line_input_width)
        self.ttplBoxInput3.setFrame(False)
        lout_2.setSpacing(0)
        lout_2.addWidget(qt.QLabel(u"Ttpl, \u2103 : "))
        lout_2.addWidget(self.ttplBoxLabl2)
        lout_2.addWidget(qt.QLabel(" = "))
        lout_2.addWidget(self.ttplBoxInput2)
        lout_2.addWidget(qt.QLabel(u" \u2219 Utpl + "))
        lout_2.addWidget(self.ttplBoxInput3)
        lout_2.addWidget(qt.QLabel(u" \u2219 "))
        lout_2.addWidget(qt.QLabel("Utpl<sup>2</sup>"))
        lout_2.addStretch()

        self.uhtrBox = qt.QGroupBox("Modulation heater rel. voltage")
        mainLayout.addWidget(self.uhtrBox)
        lout_0 = qt.QHBoxLayout()
        self.uhtrBox.setLayout(lout_0)
        self.uhtrBoxLabl1 = qt.QLabel("000.000")
        self.uhtrBoxLabl2 = qt.QLabel("000.000")
        self.uhtrBoxInput1 = qt.QLineEdit()
        self.uhtrBoxInput1.setMaximumWidth(short_line_input_width)
        self.uhtrBoxInput1.setFrame(False)
        self.uhtrBoxInput2 = qt.QLineEdit()
        self.uhtrBoxInput2.setMaximumWidth(short_line_input_width)
        self.uhtrBoxInput2.setFrame(False)
        self.uhtrBoxResetButton = qt.QPushButton("->0")
        self.uhtrBoxResetButton.setFixedWidth(25)
        self.uhtrBoxResetButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_0.setSpacing(0)
        lout_0.addWidget(qt.QLabel("Uhtr, mV : "))
        lout_0.addWidget(self.uhtrBoxLabl1)
        lout_0.addWidget(qt.QLabel(" = ( "))
        lout_0.addWidget(self.uhtrBoxLabl2)
        lout_0.addWidget(qt.QLabel(" + "))
        lout_0.addWidget(self.uhtrBoxInput1)
        lout_0.addWidget(qt.QLabel(u" ) \u2219 "))
        lout_0.addWidget(self.uhtrBoxInput2)
        lout_0.addStretch()
        lout_0.addWidget(self.uhtrBoxResetButton)
        
        self.ihtrBox = qt.QGroupBox("Modulation heater current")
        mainLayout.addWidget(self.ihtrBox)
        lout_0 = qt.QHBoxLayout()
        self.ihtrBox.setLayout(lout_0)
        self.ihtrBoxLabl1 = qt.QLabel("000.000")
        self.ihtrBoxInput1 = qt.QLineEdit()
        self.ihtrBoxInput1.setMaximumWidth(short_line_input_width)
        self.ihtrBoxInput1.setFrame(False)
        self.ihtrBoxInput2 = qt.QLineEdit()
        self.ihtrBoxInput2.setMaximumWidth(short_line_input_width)
        self.ihtrBoxInput2.setFrame(False)
        self.ihtrBoxLabl2 = qt.QLabel("000.000")
        lout_0.setSpacing(0)
        lout_0.addWidget(qt.QLabel("Ihtr, mA : "))
        lout_0.addWidget(self.ihtrBoxLabl1)
        lout_0.addWidget(qt.QLabel(" = "))
        lout_0.addWidget(self.ihtrBoxInput1)
        lout_0.addWidget(qt.QLabel(" + "))
        lout_0.addWidget(self.ihtrBoxInput2)
        lout_0.addWidget(qt.QLabel(u" \u2219 "))
        lout_0.addWidget(self.ihtrBoxLabl2)
        lout_0.addStretch()
        
        self.thtrBox = qt.QGroupBox("Modulation heater temperature")
        mainLayout.addWidget(self.thtrBox)
        lout_0 = qt.QVBoxLayout()
        self.thtrBox.setLayout(lout_0)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        self.thtrBoxLabl1 = qt.QLabel("000.000")
        lout_1.setSpacing(0)
        lout_1.addWidget(qt.QLabel(u"R, \u03A9 : "))
        lout_1.addWidget(self.thtrBoxLabl1)
        lout_1.addStretch()
        lout_2 = qt.QHBoxLayout()
        lout_0.addLayout(lout_2)
        self.thtrBoxLabl2 = qt.QLabel("000.000")
        self.thtrBoxInput1 = qt.QLineEdit()
        self.thtrBoxInput1.setMaximumWidth(short_line_input_width)
        self.thtrBoxInput1.setFrame(False)
        self.thtrBoxInput2 = qt.QLineEdit()
        self.thtrBoxInput2.setMaximumWidth(short_line_input_width)
        self.thtrBoxInput2.setFrame(False)
        self.thtrBoxInput3 = qt.QLineEdit()
        self.thtrBoxInput3.setMaximumWidth(short_line_input_width)
        self.thtrBoxInput3.setFrame(False)
        lout_2.setSpacing(0)
        lout_2.addWidget(qt.QLabel(u"Thtr, \u2103 : "))
        lout_2.addWidget(self.thtrBoxLabl2)
        lout_2.addWidget(qt.QLabel(" = "))
        lout_2.addWidget(self.thtrBoxInput1)
        lout_2.addWidget(qt.QLabel(" + "))
        lout_2.addWidget(self.thtrBoxInput2)
        lout_2.addWidget(qt.QLabel(u" \u2219 R + "))
        lout_2.addWidget(self.thtrBoxInput3)
        lout_2.addWidget(qt.QLabel(u" \u2219 ")) 
        lout_2.addWidget(qt.QLabel("R<sup>2</sup>"))
        lout_2.addStretch()

        self.thtrdBox = qt.QGroupBox("Dynamic modulation heater temperature")
        mainLayout.addWidget(self.thtrdBox)
        lout_0 = qt.QVBoxLayout()
        self.thtrdBox.setLayout(lout_0)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        self.thtrdBoxLabl1 = qt.QLabel("000.000")
        self.thtrdBoxLabl2 = qt.QLabel("000.000")
        lout_1.setSpacing(0)
        lout_1.addWidget(qt.QLabel(u"R, \u03A9 : "))
        lout_1.addWidget(self.thtrdBoxLabl1)
        lout_1.addWidget(qt.QLabel(" / "))
        lout_1.addWidget(self.thtrdBoxLabl2)
        lout_1.addStretch()
        lout_2 = qt.QHBoxLayout()
        lout_0.addLayout(lout_2)
        self.thtrdBoxLabl2 = qt.QLabel("000.000")
        self.thtrdBoxInput1 = qt.QLineEdit()
        self.thtrdBoxInput1.setMaximumWidth(short_line_input_width)
        self.thtrdBoxInput1.setFrame(False)
        self.thtrdBoxInput2 = qt.QLineEdit()
        self.thtrdBoxInput2.setMaximumWidth(short_line_input_width)
        self.thtrdBoxInput2.setFrame(False)
        self.thtrdBoxInput3 = qt.QLineEdit()
        self.thtrdBoxInput3.setMaximumWidth(short_line_input_width)
        self.thtrdBoxInput3.setFrame(False)
        lout_2.setSpacing(0)
        lout_2.addWidget(qt.QLabel(u"Thtrd, \u2103 : "))
        lout_2.addWidget(self.thtrdBoxLabl2)
        lout_2.addWidget(qt.QLabel(" = "))
        lout_2.addWidget(self.thtrdBoxInput1)
        lout_2.addWidget(qt.QLabel(" + "))
        lout_2.addWidget(self.thtrdBoxInput2)
        lout_2.addWidget(qt.QLabel(u" \u2219 R + "))
        lout_2.addWidget(self.thtrdBoxInput3)
        lout_2.addWidget(qt.QLabel(u" \u2219 "))
        lout_2.addWidget(qt.QLabel("R<sup>2</sup>"))
        lout_2.addStretch()        
        
        self.theaterBox = qt.QGroupBox("Heater temperature vs heater voltage")
        mainLayout.addWidget(self.theaterBox)
        lout_0 = qt.QVBoxLayout()
        self.theaterBox.setLayout(lout_0)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        lout_2 = qt.QHBoxLayout()
        lout_0.addLayout(lout_2) 
        self.theaterBoxInput1 = qt.QLineEdit()
        self.theaterBoxInput1.setMaximumWidth(short_line_input_width)
        self.theaterBoxInput1.setFrame(False)
        self.theaterBoxInput2 = qt.QLineEdit()
        self.theaterBoxInput2.setMaximumWidth(short_line_input_width)
        self.theaterBoxInput2.setFrame(False)
        self.theaterBoxInput3 = qt.QLineEdit()
        self.theaterBoxInput3.setMaximumWidth(short_line_input_width)
        self.theaterBoxInput3.setFrame(False)
        self.theaterBoxInput4 = qt.QLineEdit()
        self.theaterBoxInput4.setMaximumWidth(short_line_input_width)
        self.theaterBoxInput4.setFrame(False)
        lout_1.setSpacing(0)
        lout_1.addWidget(qt.QLabel(u"Safe voltage, V = "))
        lout_1.addWidget(self.theaterBoxInput1)
        lout_1.addStretch()
        lout_2.setSpacing(0)
        lout_2.addWidget(qt.QLabel(u"Theater, \u2103 = "))
        lout_2.addWidget(self.theaterBoxInput2)
        lout_2.addWidget(qt.QLabel(u" \u2219 U + "))
        lout_2.addWidget(self.theaterBoxInput3)
        lout_2.addWidget(qt.QLabel(u" \u2219 "))
        lout_2.addWidget(qt.QLabel("U<sup>2</sup> + "))
        lout_2.addWidget(self.theaterBoxInput4)
        lout_2.addWidget(qt.QLabel(u" \u2219 "))
        lout_2.addWidget(qt.QLabel("U<sup>3</sup>"))
        lout_2.addStretch()  

        self.rhtrBox = qt.QGroupBox("Heaters resistance")
        mainLayout.addWidget(self.rhtrBox)
        lout_0 = qt.QHBoxLayout()
        self.rhtrBox.setLayout(lout_0)
        lout_0.setSpacing(0)
        lout_0.addWidget(qt.QLabel(u"R<sub>inner</sub>, \u03A9 = "))
        self.rhtrBoxInput1 = qt.QLineEdit()
        self.rhtrBoxInput1.setMaximumWidth(short_line_input_width)
        self.rhtrBoxInput1.setFrame(False)
        lout_0.addWidget(self.rhtrBoxInput1)
        lout_0.addSpacing(20)
        lout_0.addWidget(qt.QLabel(u"R<sub>guard</sub>, \u03A9 = "))
        self.rhtrBoxInput2 = qt.QLineEdit()
        self.rhtrBoxInput2.setMaximumWidth(short_line_input_width)
        self.rhtrBoxInput2.setFrame(False)
        lout_0.addWidget(self.rhtrBoxInput2)
        lout_0.addStretch()

        self.amplcorBox = qt.QGroupBox("Amplitude correction")
        mainLayout.addWidget(self.amplcorBox)
        lout_0 = qt.QHBoxLayout()
        self.amplcorBox.setLayout(lout_0)
        self.amplcorBoxInput1 = qt.QLineEdit()
        self.amplcorBoxInput1.setMaximumWidth(short_line_input_width)
        self.amplcorBoxInput1.setFrame(False)
        self.amplcorBoxInput2 = qt.QLineEdit()
        self.amplcorBoxInput2.setMaximumWidth(short_line_input_width)
        self.amplcorBoxInput2.setFrame(False)
        self.amplcorBoxInput3 = qt.QLineEdit()
        self.amplcorBoxInput3.setMaximumWidth(short_line_input_width)
        self.amplcorBoxInput3.setFrame(False)
        self.amplcorBoxInput4 = qt.QLineEdit()
        self.amplcorBoxInput4.setMaximumWidth(short_line_input_width)
        self.amplcorBoxInput4.setFrame(False)
        lout_0.addWidget(qt.QLabel(u"Ac = "))
        lout_0.addWidget(self.amplcorBoxInput1)
        lout_0.addWidget(qt.QLabel(" + "))
        lout_0.addWidget(self.amplcorBoxInput2)
        lout_0.addWidget(qt.QLabel(u" \u2219 T + "))
        lout_0.addWidget(self.amplcorBoxInput3)
        lout_0.addWidget(qt.QLabel(u" \u2219 "))
        lout_0.addWidget(qt.QLabel("T<sup>2</sup> + "))
        lout_0.addWidget(self.amplcorBoxInput4)
        lout_0.addWidget(qt.QLabel(u" \u2219 "))
        lout_0.addWidget(qt.QLabel("T<sup>3</sup>"))
        lout_0.addStretch()  
        
        mainLayout.addStretch()
        mainLayout.addStretch()
        hline = qt.QFrame()
        hline.setFrameShape(qt.QFrame.HLine)
        hline.setStyleSheet("color: rgb(220, 220, 220);")
        mainLayout.addWidget(hline)

        lout_1 = qt.QHBoxLayout()
        mainLayout.addLayout(lout_1)
        lout_1.setSpacing(1)
        self.loadCalibButton = qt.QPushButton("Load && Apply")
        lout_1.addWidget(self.loadCalibButton)
        self.saveCalibButton = qt.QPushButton("Save && Apply")
        lout_1.addWidget(self.saveCalibButton)
        self.runCalibrationButton = qt.QPushButton("Calibration...")
        self.runCalibrationButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.addWidget(self.runCalibrationButton)
        self.resetCalibButton = qt.QPushButton("Reset")
        self.resetCalibButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.addWidget(self.resetCalibButton)


        float_validator = qt.QRegExpValidator(qt.QRegExp("^[-]{0,1}[0-9]{1,5}\.[0-9]{1,10}$|^[-]{0,1}[0-9]{1,5}\.[0-9]{1,10}e[-]{0,1}[+]{0,1}[0-9]{0,2}$"))
        self.update_calib_input_fields()
        for item in self.findChildren(qt.QPushButton):
            item.setFocusPolicy(qt.Qt.NoFocus)
        for item in self.findChildren(qt.QLineEdit):
            item.setAlignment(qt.Qt.AlignCenter)
            item.setCursorPosition(0)
            item.setMinimumWidth(short_line_input_width)
            item.setMaximumWidth(16777215)
            policy = item.sizePolicy()
            policy.setHorizontalPolicy(qt.QSizePolicy.Expanding)
            item.setSizePolicy(policy)
            if item != self.calibInfoInput:
                item.setValidator(float_validator)
                
        # ####### end of UI setup
        # ########################################
        
        self.loadCalibButton.clicked.connect(self.load_calib_from_file)
        self.resetCalibButton.clicked.connect(self.reset_calib)
        self.saveCalibButton.clicked.connect(self.save_calib_to_file)
        self.runCalibrationButton.clicked.connect(self.start_calibration_procedure)
        self.ttplBoxResetButton.clicked.connect(self.zero_utpl_offset)
        self.uhtrBoxResetButton.clicked.connect(self.zero_uhtr_offset)
        self.refreshCalibrationFilesButton.clicked.connect(self.refresh_calibration_files)
        self.calibrationFilesCombo.currentIndexChanged.connect(self.on_calibration_file_selected)
        for item in self.findChildren(qt.QLineEdit):
            if item is not self.calibInfoInput:
                item.editingFinished.connect(self.apply_calib_from_fields)

        self._updating_calibration_files = False
        self.refresh_calibration_files()

    def _calibration_directory(self):
        """Returns the directory used to populate the calibration file dropdown."""
        current_path = self.parent().calibPathInput.text().strip() if self.parent() is not None else ''
        if current_path:
            if os.path.isdir(current_path):
                return current_path
            directory = os.path.dirname(current_path)
            if directory:
                return directory
        return os.path.dirname(str(self.parent().calibPathInput.text().strip())) or os.getcwd()

    def refresh_calibration_files(self):
        """Refreshes the dropdown list of calibration files from the calibration folder."""
        directory = self._calibration_directory()
        if not directory or not os.path.isdir(directory):
            return
        current_path = os.path.abspath(self.parent().calibPathInput.text().strip()) if self.parent() is not None and self.parent().calibPathInput.text().strip() else ''
        self._updating_calibration_files = True
        try:
            self.calibrationFilesCombo.clear()
            files = sorted(name for name in os.listdir(directory) if name.lower().endswith('.json'))
            for name in files:
                full_path = os.path.abspath(os.path.join(directory, name))
                self.calibrationFilesCombo.addItem(name, full_path)
            if current_path:
                index = self.calibrationFilesCombo.findData(current_path)
                if index >= 0:
                    self.calibrationFilesCombo.setCurrentIndex(index)
        finally:
            self._updating_calibration_files = False

    def on_calibration_file_selected(self, index):
        """Synchronizes the selected dropdown calibration file with the main window path field."""
        if self._updating_calibration_files or index < 0 or self.parent() is None:
            return
        path = self.calibrationFilesCombo.itemData(index)
        if path:
            self.parent().calibPathInput.setText(str(path))

    def load_calib_from_file(self):
        """????????? ?????? `load_calib_from_file`."""
        try:
            if self.calibrationFilesCombo.count() and self.calibrationFilesCombo.currentIndex() >= 0:
                selected_path = self.calibrationFilesCombo.currentData()
                if selected_path:
                    self.parent().calibPathInput.setText(str(selected_path))
            else:
                self.parent().select_calibration_file()
            self.parent().apply_calibration()
            self.refresh_calibration_files()
            self.update_calib_input_fields()
            logging.info("Calibration loaded and applied successfully.")
        except Exception as e:
            logging.error(f"Failed to load calibration from file: {e}")
            ErrorWindow(f"Failed to load calibration: {e}")

    def save_calib_to_file(self, fpath=False):
        """????????? ?????? `save_calib_to_file`."""
        try:
            fpath = qt.QFileDialog.getSaveFileName(
                self,
                "Select file and path to save calibration:",
                None,
                "*.json",
                options=_dialog_options(),
            )[0]
            if fpath:
                self.read_calib_input_fields()
                calibration_data = self.parent().calibration.to_file_dict()
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(calibration_data, f, indent=4, ensure_ascii=False)
                self.parent().set_active_calibration(self.parent().calibration, path=fpath)
                self.refresh_calibration_files()
                logging.info(f"Calibration saved to {fpath}.")
        except Exception as e:
            logging.error(f"Failed to save calibration to file: {e}")
            ErrorWindow(f"Failed to save calibration: {e}")

    def reset_calib(self):
        """?????????? ?????? `reset_calib`."""
        self.parent().apply_default_calib()

    def start_calibration_procedure(self):
        """Starts the interactive calibration workflow from the calibration window."""
        try:
            self.read_calib_input_fields()
            self.parent().start_calibration_wizard()
        except Exception as e:
            logging.error(f"Failed to start calibration procedure: {e}")
            ErrorWindow(f"Failed to start calibration procedure: {e}")

    def apply_calib_from_fields(self):
        """????????? ?????? `apply_calib_from_fields`."""
        try:
            self.read_calib_input_fields()
            self.parent().set_active_calibration(
                self.parent().calibration,
                path=self.parent().calibPathInput.text().strip() or None,
            )
        except Exception as e:
            logging.error(f"Failed to apply calibration from fields: {e}")
            ErrorWindow(f"Failed to apply calibration: {e}")

    def _set_live_label(self, key, value, precision=4):
        label = self.live_value_labels.get(key)
        if label is None:
            return
        try:
            if value is None:
                raise ValueError
            label.setText(f"{float(value):.{precision}f}")
        except Exception:
            label.setText("---")

    def update_live_measurements(self, metrics=None):
        metrics = metrics or {}
        self._set_live_label('utpl_raw', metrics.get('UtplRaw'), 4)
        self._set_live_label('ttpl_cal', metrics.get('Ttpl'), 4)
        self._set_live_label('uhtr_raw', metrics.get('UhtrRaw'), 4)
        self._set_live_label('uhtr_cal', metrics.get('Uhtr'), 4)
        self._set_live_label('ihtr_raw', metrics.get('IhtrRaw'), 6)
        self._set_live_label('ihtr_cal', metrics.get('Ihtr'), 6)
        self._set_live_label('rhtr', metrics.get('Rhtr'), 4)
        self._set_live_label('thtr', metrics.get('Thtr'), 4)
        self._set_live_label('rhtrd', metrics.get('Rhtrd'), 4)
        self._set_live_label('thtrd', metrics.get('Thtrd'), 4)

        try:
            self.ttplBoxLabl1.setText(f"{float(metrics.get('UtplRaw', 0.0)):.4f}")
            self.ttplBoxLabl2.setText(f"{float(metrics.get('Ttpl', 0.0)):.4f}")
            self.uhtrBoxLabl1.setText(f"{float(metrics.get('Uhtr', 0.0)):.4f}")
            self.uhtrBoxLabl2.setText(f"{float(metrics.get('UhtrRaw', 0.0)):.4f}")
            self.ihtrBoxLabl1.setText(f"{float(metrics.get('Ihtr', 0.0)):.6f}")
            self.ihtrBoxLabl2.setText(f"{float(metrics.get('IhtrRaw', 0.0)):.6f}")
            self.thtrBoxLabl1.setText(f"{float(metrics.get('Rhtr', 0.0)):.4f}")
            self.thtrBoxLabl2.setText(f"{float(metrics.get('Thtr', 0.0)):.4f}")
            self.thtrdBoxLabl1.setText(f"{float(metrics.get('Rhtrd', 0.0)):.4f}")
            self.thtrdBoxLabl2.setText(f"{float(metrics.get('Thtrd', 0.0)):.4f}")
        except Exception:
            pass

    def zero_utpl_offset(self):
        try:
            raw = float(self.live_value_labels['utpl_raw'].text())
        except Exception:
            raw = 0.0
        self.ttplBoxInput1.setText(str(round(-raw, 10)))
        self.apply_calib_from_fields()

    def zero_uhtr_offset(self):
        try:
            raw = float(self.live_value_labels['uhtr_raw'].text())
        except Exception:
            raw = 0.0
        self.uhtrBoxInput1.setText(str(round(-raw, 10)))
        self.apply_calib_from_fields()

    def update_calib_input_fields(self):
        """Обновить поля ввода информации о калибровке."""
        try:
            calibration = self.parent().calibration
            self.calibInfoInput.setText(str(calibration.comment))
            self.ttplBoxInput1.setText(str(round(calibration.utpl0, 10)))
            self.ttplBoxInput2.setText(str(round(calibration.ttpl0, 10)))
            self.ttplBoxInput3.setText(str(round(calibration.ttpl1, 10)))
            self.uhtrBoxInput1.setText(str(round(calibration.uhtr0, 10)))
            self.uhtrBoxInput2.setText(str(round(calibration.uhtr1, 10)))
            self.ihtrBoxInput1.setText(str(round(calibration.ihtr0, 10)))
            self.ihtrBoxInput2.setText(str(round(calibration.ihtr1, 10)))
            self.thtrBoxInput1.setText(str(round(calibration.thtr0, 10)))
            self.thtrBoxInput2.setText(str(round(calibration.thtr1, 10)))
            self.thtrBoxInput3.setText(str(round(calibration.thtr2, 10)))
            self.thtrdBoxInput1.setText(str(round(calibration.thtrd0, 10)))
            self.thtrdBoxInput2.setText(str(round(calibration.thtrd1, 10)))
            self.thtrdBoxInput3.setText(str(round(calibration.thtrd2, 10)))
            self.theaterBoxInput1.setText(str(round(calibration.safe_voltage, 10)))
            self.refresh_calibration_files()
            self.theaterBoxInput2.setText(str(round(calibration.theater0, 10)))
            self.theaterBoxInput3.setText(str(round(calibration.theater1, 10)))
            self.theaterBoxInput4.setText(str(round(calibration.theater2, 10)))
            self.rhtrBoxInput1.setText(str(round(calibration.rhtr, 10)))
            self.rhtrBoxInput2.setText(str(round(calibration.rghtr, 10)))
            self.amplcorBoxInput1.setText(str(round(calibration.ac0, 10)))
            self.amplcorBoxInput2.setText(str(round(calibration.ac1, 10)))
            self.amplcorBoxInput3.setText(str(round(calibration.ac2, 10)))
            self.amplcorBoxInput4.setText(str(round(calibration.ac3, 10)))
        except Exception as e:
            logging.error(f"Failed to update calibration input fields: {e}")
            ErrorWindow(f"Failed to update calibration input fields: {e}")

    def read_calib_input_fields(self):
        """?????? ?????? `read_calib_input_fields`."""
        calibration = self.parent().calibration
        calibration.comment = self.calibInfoInput.text()
        calibration.utpl0 = float(self.ttplBoxInput1.text() or 0)
        calibration.ttpl0 = float(self.ttplBoxInput2.text() or 0)
        calibration.ttpl1 = float(self.ttplBoxInput3.text() or 0)
        calibration.uhtr0 = float(self.uhtrBoxInput1.text() or 0)
        calibration.uhtr1 = float(self.uhtrBoxInput2.text() or 0)
        calibration.ihtr0 = float(self.ihtrBoxInput1.text() or 0)
        calibration.ihtr1 = float(self.ihtrBoxInput2.text() or 0)
        calibration.thtr0 = float(self.thtrBoxInput1.text() or 0)
        calibration.thtr1 = float(self.thtrBoxInput2.text() or 0)
        calibration.thtr2 = float(self.thtrBoxInput3.text() or 0)
        calibration.thtrd0 = float(self.thtrdBoxInput1.text() or 0)
        calibration.thtrd1 = float(self.thtrdBoxInput2.text() or 0)
        calibration.thtrd2 = float(self.thtrdBoxInput3.text() or 0)
        calibration.safe_voltage = float(self.theaterBoxInput1.text() or 0)
        calibration.theater0 = float(self.theaterBoxInput2.text() or 0)
        calibration.theater1 = float(self.theaterBoxInput3.text() or 0)
        calibration.theater2 = float(self.theaterBoxInput4.text() or 0)
        calibration.rhtr = float(self.rhtrBoxInput1.text() or 0)
        calibration.rghtr = float(self.rhtrBoxInput2.text() or 0)
        calibration.ac0 = float(self.amplcorBoxInput1.text() or 0)
        calibration.ac1 = float(self.amplcorBoxInput2.text() or 0)
        calibration.ac2 = float(self.amplcorBoxInput3.text() or 0)
        calibration.ac3 = float(self.amplcorBoxInput4.text() or 0)
        calibration._add_params()

'''if __name__ == "__main__":
    import sys
    app = qt.QApplication(sys.argv)
    example = calibWindow()
    example.show()
    sys.exit(app.exec())'''





class ErrorWindow(qt.QMessageBox):
    def __init__(self, error_text: str, parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super(ErrorWindow, self).__init__(parent)
        _make_window_modal(self)
        self.setText(error_text)
        self.setWindowTitle(tr("Error"))
        self.setIcon(qt.QMessageBox.Critical)
        self.addButton(qt.QMessageBox.Ok)
        self.exec()

class MessageWindow(qt.QMessageBox):
    def __init__(self, message_text: str, parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super(MessageWindow, self).__init__(parent)
        _make_window_modal(self)
        self.setText(message_text)
        self.setWindowTitle(tr("Sorry..."))
        self.setIcon(qt.QMessageBox.Information)
        self.addButton(qt.QMessageBox.Ok)
        self.exec()

class YesCancelWindow(qt.QMessageBox):
    def __init__(self, message_text: str, parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super(YesCancelWindow, self).__init__(parent)
        _make_window_modal(self)
        self.setText(message_text)
        self.setWindowTitle(tr("Warning"))
        self.setIcon(qt.QMessageBox.Warning)
        self.addButton(qt.QMessageBox.Yes)
        self.addButton(qt.QMessageBox.Cancel)










class configWindow(qt.QDialog):
    def __init__(self, parent=None):
        """?????????????? ?????? ? ?????????????? ??? ?????????."""
        super(configWindow, self).__init__(parent=parent)

        # ####### UI setup
        # ########################################
        self.setWindowTitle(tr("Help & Configuration"))
        self.setFixedHeight(400)
        self.setFixedWidth(300)
        _make_window_modal(self)

        mainLayout = qt.QVBoxLayout()
        mainLayout.setAlignment(qt.Qt.AlignHCenter)
        self.setLayout(mainLayout)

        labl = qt.QLabel("Some help will be here :)")
        labl.setAlignment(qt.Qt.AlignHCenter)
        mainLayout.addWidget(labl)
        labl = qt.QLabel("Nanocontrol v.0.1")
        labl.setAlignment(qt.Qt.AlignHCenter)
        labl.setFont(qt.QFont("Times", weight=qt.QFont.Bold))
        mainLayout.addWidget(labl)
        labl = qt.QLabel("Melnikov Alexey & Komov Evgenii")
        labl.setAlignment(qt.Qt.AlignHCenter)
        mainLayout.addWidget(labl)
        labl = qt.QLabel(u"<p><a href='"'mailto:alexey.melnikov@esrf.fr'"'>alexey.melnikov@esrf.fr</a>  </p>")
        labl.setAlignment(qt.Qt.AlignHCenter)
        mainLayout.addWidget(labl)

        ######## Configuration parameters
        mainLayout.addStretch()
        mainLayout.addStretch()
        self.configGroupBox = qt.QGroupBox()
        mainLayout.addWidget(self.configGroupBox)

        lout_0 = qt.QVBoxLayout()
        lout_0.setSpacing(2)
        self.configGroupBox.setLayout(lout_0)
        labl = qt.QLabel("Configuration parameters")
        labl.setAlignment(qt.Qt.AlignHCenter)
        labl.setFont(qt.QFont("Times", weight=qt.QFont.Bold))
        lout_0.addWidget(labl)
        lout_0.addSpacing(10)

        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        labl = qt.QLabel("Tango host: ")
        labl.setMinimumWidth(75)
        lout_1.addWidget(labl)
        self.tangoHostInput = qt.QLineEdit()
        self.tangoHostInput.setFrame(False)
        self.tangoHostInput.setText(self.parent().settings.tango_host)
        lout_1.addWidget(self.tangoHostInput)

        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        labl = qt.QLabel("Device proxy: ")
        labl.setMinimumWidth(75)
        lout_1.addWidget(labl)
        self.deviceProxyInput = qt.QLineEdit()
        self.deviceProxyInput.setFrame(False)
        self.deviceProxyInput.setText(self.parent().settings.device_proxy)
        lout_1.addWidget(self.deviceProxyInput)

        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        labl = qt.QLabel("HTTP host: ")
        labl.setMinimumWidth(75)
        lout_1.addWidget(labl)
        self.httpHostInput = qt.QLineEdit()
        self.httpHostInput.setFrame(False)
        self.httpHostInput.setText(self.parent().settings.http_host)
        lout_1.addWidget(self.httpHostInput)

        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.setSpacing(1)
        self.applyConfigButton = qt.QPushButton("Apply")
        self.applyConfigButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.addWidget(self.applyConfigButton)
        self.loadConfigButton = qt.QPushButton("Load")
        self.loadConfigButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.addWidget(self.loadConfigButton)
        self.saveConfigButton = qt.QPushButton("Save")
        self.saveConfigButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.addWidget(self.saveConfigButton)
        self.resetConfigButton = qt.QPushButton("Reset")
        self.resetConfigButton.setFocusPolicy(qt.Qt.NoFocus)
        lout_1.addWidget(self.resetConfigButton)

        if parent.sysNoHardware.isChecked() == True:
            self.configGroupBox.setEnabled(False)
            self.httpHostInput.setText("no-hardware mode")
            self.deviceProxyInput.setText("no-hardware mode")
            self.tangoHostInput.setText("no-hardware mode")

        # ####### end of UI setup
        # ########################################
        self.applyConfigButton.clicked.connect(self.apply_settings)
        self.saveConfigButton.clicked.connect(self.save_settings_to_file)
        self.loadConfigButton.clicked.connect(self.load_settings_from_file)
        self.resetConfigButton.clicked.connect(self.reset_settings)

    def apply_settings(self):
        """????????? ?????? `apply_settings`."""
        self.parent().settings.tango_host = self.tangoHostInput.text()
        self.parent().settings.device_proxy = self.deviceProxyInput.text()
        self.parent().settings.http_host = self.httpHostInput.text()

    def load_settings_from_file(self):
        """????????? ?????? `load_settings_from_file`."""
        self.parent().load_settings_from_file(fpath=True)
        self.tangoHostInput.setText(self.parent().settings.tango_host)
        self.deviceProxyInput.setText(self.parent().settings.device_proxy)
        self.httpHostInput.setText(self.parent().settings.http_host)

    def save_settings_to_file(self):
        """????????? ?????? `save_settings_to_file`."""
        self.parent().save_settings_to_file(fpath=True)
    
    def reset_settings(self):
        """?????????? ?????? `reset_settings`."""
        self.parent().reset_settings()
        self.tangoHostInput.setText(self.parent().settings.tango_host)
        self.deviceProxyInput.setText(self.parent().settings.device_proxy)
        self.httpHostInput.setText(self.parent().settings.http_host)
