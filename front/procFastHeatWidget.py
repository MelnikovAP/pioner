import numpy as np
from silx.gui import qt
from silx.io import open
from silx.math.fit import filters
import h5py
from shutil import copy
import json

from messageWindows import *
from calibWindow import *
from resultsDataWidget import resultsDataWidget


class procFastHeatWidget(qt.QWidget):
    def __init__(self, parent=None):
        super(procFastHeatWidget, self).__init__(parent=parent)

        # ####### UI setup
        # ########################################
        short_line_input_width = 60

        main_lout = qt.QHBoxLayout()
        self.setLayout(main_lout)
        
        left_lout = qt.QVBoxLayout()
        right_lout = qt.QVBoxLayout()
        left_lout.setSpacing(0)
        right_lout.setSpacing(0)
        main_lout.addLayout(left_lout, 0)
        main_lout.addLayout(right_lout, 1)

        ## Experiment files management table
        left_lout.addWidget(qt.QLabel("Experimental data"))
        self.expFilesTable = qt.QListWidget()
        self.expFilesTable.setFixedSize(200, 200)
        self.expFilesTable.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
        left_lout.addWidget(self.expFilesTable, 0)

        lout_0 = qt.QHBoxLayout()
        left_lout.addLayout(lout_0)
        self.averageButtonExpFilesTable = qt.QPushButton("Average")
        self.averageButtonExpFilesTable.setEnabled(False)
        self.removeButtonExpFilesTable = qt.QPushButton("-")
        self.removeButtonExpFilesTable.setFixedWidth(30)
        self.removeButtonExpFilesTable.setEnabled(False)
        self.addButtonExpFilesTable = qt.QPushButton("+")
        self.addButtonExpFilesTable.setFixedWidth(30)
        lout_0.addWidget(self.averageButtonExpFilesTable)
        lout_0.addStretch()
        lout_0.addWidget(self.removeButtonExpFilesTable)
        lout_0.addWidget(self.addButtonExpFilesTable)

        left_lout.addSpacing(10)

        ## Reference files management table
        left_lout.addWidget(qt.QLabel("Reference data"))
        self.emptyFilesTable = qt.QListWidget()
        self.emptyFilesTable.setFixedSize(200, 200)
        self.emptyFilesTable.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
        left_lout.addWidget(self.emptyFilesTable, 0)

        lout_0 = qt.QHBoxLayout()
        left_lout.addLayout(lout_0)
        self.averageButtonEmptyFilesTable = qt.QPushButton("Average")
        self.averageButtonEmptyFilesTable.setEnabled(False)
        self.removeButtonEmptyFilesTable = qt.QPushButton("-")
        self.removeButtonEmptyFilesTable.setFixedWidth(30)
        self.removeButtonEmptyFilesTable.setEnabled(False)
        self.addButtonEmptyFilesTable = qt.QPushButton("+")
        self.addButtonEmptyFilesTable.setFixedWidth(30)
        lout_0.addWidget(self.averageButtonEmptyFilesTable)
        lout_0.addStretch()
        lout_0.addWidget(self.removeButtonEmptyFilesTable)
        lout_0.addWidget(self.addButtonEmptyFilesTable)

        left_lout.addStretch()

        ## Left control buttons
        lout_0 = qt.QHBoxLayout()
        left_lout.addLayout(lout_0)
        self.plotButton = qt.QPushButton("Plot")
        self.plotButton.setEnabled(False)
        self.saveResultsButton = qt.QPushButton("Save")
        self.saveResultsButton.setEnabled(False)
        lout_0.addWidget(self.saveResultsButton)
        lout_0.addWidget(self.plotButton)

        ## Graph space
        self.procFastHeatGraph = resultsDataWidget(parent=self)
        self.procFastHeatGraph.curveLegendsWidgetDock.setHidden(True)
        self.graphRoiManager = self.procFastHeatGraph.roiManager
        right_lout.addWidget(self.procFastHeatGraph, 1)
        
        ## Calibration space
        
        self.calibrationGroupBox = qt.QGroupBox("Calibration coefficients")
        right_lout.addWidget(self.calibrationGroupBox)
        lout_1 = qt.QHBoxLayout()
        self.calibrationGroupBox.setLayout(lout_1)
        lout_1.setSpacing(1)
        lout_1.addWidget(qt.QLabel("R<sub>h</sub>(T) = "))
        self.rcoeff1Input = qt.QLineEdit()
        self.rcoeff1Input.setFixedWidth(short_line_input_width)
        lout_1.addWidget(self.rcoeff1Input)
        lout_1.addWidget(qt.QLabel(" + T \u2219"))
        self.rcoeff2Input = qt.QLineEdit()
        self.rcoeff2Input.setFixedWidth(short_line_input_width)
        lout_1.addWidget(self.rcoeff2Input)
        lout_1.addWidget(qt.QLabel(" + T<sup>2</sup> \u2219"))
        self.rcoeff3Input = qt.QLineEdit()
        self.rcoeff3Input.setFixedWidth(short_line_input_width)
        lout_1.addWidget(self.rcoeff3Input)
        lout_1.addStretch()
        lout_1.addSpacing(short_line_input_width)
        lout_1.addWidget(qt.QLabel("R<sub>g</sub> = "))
        self.rgRhRatioInput = qt.QLineEdit()
        self.rgRhRatioInput.setFixedWidth(short_line_input_width)
        lout_1.addWidget(self.rgRhRatioInput)
        lout_1.addWidget(qt.QLabel(" \u2219 R<sub>h</sub> "))

        ## Correction space
        lout_0 = qt.QHBoxLayout()
        right_lout.addLayout(lout_0)
        self.manualCorrectionGroupBox = qt.QGroupBox("Manual correction")
        lout_0.addWidget(self.manualCorrectionGroupBox)
        lout_0.addSpacing(10)
        self.autoCorrectionGroupBox = qt.QGroupBox("Auto correction")
        lout_0.addWidget(self.autoCorrectionGroupBox)

        ## Manual Correction space
        lout_0 = qt.QVBoxLayout()
        self.manualCorrectionGroupBox.setLayout(lout_0)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.addStretch()
        lout_1.addWidget(qt.QLabel('smooth factor: '))
        self.smoothInput = qt.QSpinBox()
        self.smoothInput.setMinimum(3)
        self.smoothInput.setMaximum(100)
        self.smoothInput.setValue(10)
        self.smoothInput.setFixedWidth(short_line_input_width)
        lout_1.addWidget(self.smoothInput)
        self.displayRateButton = qt.QPushButton("Display rate")
        lout_1.addWidget(self.displayRateButton)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.addStretch()
        lout_2 = qt.QVBoxLayout()
        lout_2.setSpacing(0)
        lout_1.addLayout(lout_2)
        lout_3 = qt.QHBoxLayout()
        lout_2.addLayout(lout_3)
        lout_3.addWidget(qt.QLabel("iso begin: "))
        self.isoBeginInput = qt.QSpinBox()
        self.isoBeginInput.setMinimum(0)
        self.isoBeginInput.setMaximum(1000000000)
        self.isoBeginInput.setValue(0)
        self.isoBeginInput.setFixedWidth(short_line_input_width)
        lout_3.addWidget(self.isoBeginInput)
        lout_3 = qt.QHBoxLayout()
        lout_2.addLayout(lout_3)
        lout_3.addWidget(qt.QLabel("iso end: "))
        self.isoEndInput = qt.QSpinBox()
        self.isoEndInput.setMinimum(0)
        self.isoEndInput.setMaximum(1000000000)
        self.isoEndInput.setValue(100)
        self.isoEndInput.setFixedWidth(short_line_input_width)
        lout_3.addWidget(self.isoEndInput)
        lout_2 = qt.QVBoxLayout()
        lout_2.setSpacing(0)
        lout_1.addLayout(lout_2)
        self.isoAutoFindButton = qt.QPushButton("Auto find")
        lout_2.addWidget(self.isoAutoFindButton)
        lout_1 = qt.QHBoxLayout()
        lout_1.setSpacing(1)
        lout_0.addLayout(lout_1)
        self.saveFileOption = qt.QCheckBox()
        self.saveFileOption.setCheckState(2)
        lout_1.addWidget(self.saveFileOption)
        lout_1.addWidget(qt.QLabel("save to the source file"))
        lout_1.addStretch()
        self.calculateManualButton = qt.QPushButton("Calculate")
        lout_1.addWidget(self.calculateManualButton)
        
        ## Auto Correction space
        lout_0 = qt.QVBoxLayout()
        self.autoCorrectionGroupBox.setLayout(lout_0)
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        self.autoOption1Selector = qt.QComboBox()
        self.autoOption1Selector.addItem("all experiment files with one reference file")
        self.autoOption1Selector.addItem("each experiment file with own reference file")
        self.autoOption1Selector.addItem("each experiment file with auto-guess reference")
        lout_1.addWidget(self.autoOption1Selector)
        lout_1.addStretch()
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        self.autoOption2Selector = qt.QComboBox()
        self.autoOption2Selector.addItem("heat exchange auto calculation")
        self.autoOption2Selector.addItem("heat exchange constant value")
        lout_1.addWidget(self.autoOption2Selector)
        lout_1.addStretch()
        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        lout_2 = qt.QVBoxLayout()
        lout_1.addLayout(lout_2)
        self.heatExchLabel = qt.QLabel("Constant heat exchange:")
        lout_2.addWidget(self.heatExchLabel)
        self.heatExchInput = qt.QLineEdit()
        self.heatExchInput.setFixedWidth(short_line_input_width*2)
        self.heatExchInput.setText("5e-05")
        lout_2.addWidget(self.heatExchInput)
        lout_1.addStretch()
        self.calculateAutoButton = qt.QPushButton("Calculate")
        lout_1.addWidget(self.calculateAutoButton)

        main_lout.addStretch()

        float_validator = qt.QRegExpValidator(qt.QRegExp("^[-]{0,1}[0-9]{1,5}\.[0-9]{1,10}$|^[-]{0,1}[0-9]{1,5}\.[0-9]{1,10}e[-]{0,1}[+]{0,1}[0-9]{0,2}$"))
        for item in self.findChildren(qt.QLineEdit):
            item.setAlignment(qt.Qt.AlignCenter)
            item.setCursorPosition(0)
            item.setValidator(float_validator)
        

        ## Signals and slots
        self.addButtonExpFilesTable.clicked.connect(self.add_files_to_table)
        self.expFilesTable.itemSelectionChanged.connect(lambda: self.removeButtonExpFilesTable.setEnabled(True))
        self.expFilesTable.itemSelectionChanged.connect(lambda: self.removeButtonExpFilesTable.setEnabled(False)
                                                                    if (len(self.expFilesTable.selectedIndexes())==0) else None)
        self.removeButtonExpFilesTable.clicked.connect(self.remove_files_from_table)
        self.averageButtonExpFilesTable.clicked.connect(self.average_exp_data)
        self.expFilesTable.itemSelectionChanged.connect(lambda: self.averageButtonExpFilesTable.setEnabled(True)
                                                                    if (len(self.expFilesTable.selectedIndexes())>1) else None)
        self.expFilesTable.itemSelectionChanged.connect(lambda: self.averageButtonExpFilesTable.setEnabled(False)
                                                                    if (len(self.expFilesTable.selectedIndexes())==0) else None)

        self.addButtonEmptyFilesTable.clicked.connect(self.add_files_to_table)
        self.emptyFilesTable.itemSelectionChanged.connect(lambda: self.removeButtonEmptyFilesTable.setEnabled(True))
        self.emptyFilesTable.itemSelectionChanged.connect(lambda: self.removeButtonEmptyFilesTable.setEnabled(False)
                                                                    if (len(self.emptyFilesTable.selectedIndexes())==0) else None)
        self.removeButtonEmptyFilesTable.clicked.connect(self.remove_files_from_table)
        self.averageButtonEmptyFilesTable.clicked.connect(self.average_empty_data)
        self.emptyFilesTable.itemSelectionChanged.connect(lambda: self.averageButtonEmptyFilesTable.setEnabled(True)
                                                                    if (len(self.emptyFilesTable.selectedIndexes())>1) else None)
        self.emptyFilesTable.itemSelectionChanged.connect(lambda: self.averageButtonEmptyFilesTable.setEnabled(False)
                                                                    if (len(self.emptyFilesTable.selectedIndexes())==0) else None)

        self.displayRateButton.clicked.connect(self.display_rate_button_pressed)
        self.calculateManualButton.clicked.connect(self.calculate_manual_button_pressed)

        self.procFastHeatGraph.resultPlot.sigPlotSignal.connect(self.update_iso_inputs)
        self.isoEndInput.valueChanged.connect(self.update_graph_roi_max)
        self.isoBeginInput.valueChanged.connect(self.update_graph_roi_min)
        self.isoAutoFindButton.setEnabled(False) # TODO: remove later after finishing self.find_iso
        self.isoAutoFindButton.clicked.connect(self.find_iso)

        self.calculateAutoButton.clicked.connect(self.calculate_auto_button_pressed)

        self.groupBoxesStateInstance = GroupBoxesState(mainWindow=self)
        self.groupBoxesStateInstance.state.connect(self.autoCorrectionGroupBox.setEnabled)
        self.groupBoxesStateInstance.state.connect(self.manualCorrectionGroupBox.setEnabled)
        self.groupBoxesStateInstance.state.connect(self.calibrationGroupBox.setEnabled)

        self.heatExchFieldsStateInstance = HeatExchFieldsState(mainWindow=self)
        self.heatExchFieldsStateInstance.state.connect(self.heatExchLabel.setEnabled)
        self.heatExchFieldsStateInstance.state.connect(self.heatExchInput.setEnabled)
        self.autoOption2Selector.currentIndexChanged.connect(self.update_GUI)

        self.update_GUI()

    def add_files_to_table(self):
        # TODO: bad structure, think how to change
        # add file check - if it contains proper nanocal fast heat data 
        sender = self.sender()
        if sender == self.addButtonExpFilesTable:
            fnames = qt.QFileDialog().getOpenFileNames(self, "Select files", None, "*.h5")[0]
            exp_paths = [self.expFilesTable.item(x).text() for x in range(self.expFilesTable.count())]
            for fname in fnames:
                if fname not in exp_paths:
                    self.expFilesTable.addItem(fname)
                    self.expFilesTable.clearSelection()
        if sender == self.addButtonEmptyFilesTable:
            fnames = qt.QFileDialog().getOpenFileNames(self, "Select files", None, "*.h5")[0]
            empty_paths = [self.emptyFilesTable.item(x).text() for x in range(self.emptyFilesTable.count())]
            for fname in fnames:
                if fname not in empty_paths:
                    self.emptyFilesTable.addItem(fname)
                    self.emptyFilesTable.clearSelection()

        self.update_plot_after_add_remove()
        self.update_calib_fields_after_add_remove()
        self.update_GUI()
        
    def remove_files_from_table(self):
        # TODO: bad structure, think how to change
        sender = self.sender()
        if sender == self.removeButtonExpFilesTable:
            index_list = sorted(self.expFilesTable.selectedIndexes(), reverse=True)
            for selection in index_list:
                fname = self.expFilesTable.item(selection.row()).text()
                self.expFilesTable.model().removeRow(selection.row())
                self.expFilesTable.clearSelection()
        if sender == self.removeButtonEmptyFilesTable:
            index_list = sorted(self.emptyFilesTable.selectedIndexes(), reverse=True)
            for selection in index_list:
                fname = self.emptyFilesTable.item(selection.row()).text()
                self.emptyFilesTable.model().removeRow(selection.row())
                self.emptyFilesTable.clearSelection()
        
        sender.setEnabled(False)
        self.update_plot_after_add_remove()
        self.update_calib_fields_after_add_remove()
        self.update_GUI()

    def average_exp_data(self):  
        exp_paths = [self.expFilesTable.item(x).text() for x in range(self.expFilesTable.count())]
        if not self.check_files_before_averaging(exp_paths):
            return
        avg_fname = self.get_average_data_fname(datatype='data')
        if avg_fname: 
            self.averag_data(exp_paths, avg_fname)
            if self.sender() == self.displayRateButton:
                for _ in range(self.expFilesTable.count()):
                    self.expFilesTable.model().removeRow(0)
            if avg_fname not in exp_paths:
                self.expFilesTable.addItem(avg_fname)
            self.update_plot_after_add_remove()
            self.update_calib_fields_after_add_remove()
        self.expFilesTable.clearSelection()

        self.update_GUI()
        return avg_fname

    def average_empty_data(self):                          
        empty_paths = [self.emptyFilesTable.item(x).text() for x in range(self.emptyFilesTable.count())]
        if not self.check_files_before_averaging(empty_paths):
            return
        avg_fname = self.get_average_data_fname(datatype='empty')
        if avg_fname: 
            self.averag_data(empty_paths, avg_fname)
            if self.sender() == self.displayRateButton:
                for _ in range(self.emptyFilesTable.count()):
                        self.emptyFilesTable.model().removeRow(0)
            if avg_fname not in empty_paths:
                self.emptyFilesTable.addItem(avg_fname)
            self.update_plot_after_add_remove()
            self.update_calib_fields_after_add_remove()
        self.emptyFilesTable.clearSelection()

        self.update_GUI()

        return avg_fname

    def load_initial_data(self):
        empty_data = open(self.emptyFilesTable.item(0).text()+"::/data")
        self.empty_data = {'time': np.array(empty_data['time']),
                            'temp': np.array(empty_data['temp']),
                            'Uref': np.array(empty_data['Uref']),
                            'Thtr': np.array(empty_data['Thtr'])}
        empty_data.close()

        exp_data = open(self.expFilesTable.item(0).text()+"::/data")
        self.exp_data = {'time': np.array(exp_data['time']),
                            'temp': np.array(exp_data['temp']),
                            'Uref': np.array(exp_data['Uref']),
                            'Thtr': np.array(exp_data['Thtr'])}
        exp_data.close()

    def check_files_before_averaging(self, source_fnames:list):
        with h5py.File(source_fnames[0], 'r') as first_file:
            first_file_keys = list(first_file['data'].keys())
            first_file_data_length = len(first_file['data'][first_file_keys[0]][:])
            for fname in source_fnames[1:]:
                with h5py.File(fname, 'r') as file:
                    if list(file['data'].keys()) != first_file_keys:
                        ErrorWindow("Unable to average. Files have different structure. Probably one of them contains processed/transformed data.")
                        return
                    if len(file['data'][list(file['data'].keys())[0]][:]) != first_file_data_length:
                        ErrorWindow("Unable to average. Data in files have different length.")
                        return
        return True

    def get_average_data_fname(self, datatype:str):               
        fname = qt.QFileDialog().getSaveFileName(self, "Save average "+datatype+" as...", 
                                        "./averaged_"+datatype+".h5", 
                                        "*h5 files (*.h5)")[0]
        return fname

    def averag_data(self, source_fnames:list, dest_fname:str):  
        # copying the first file with calibration, settings and data
        # the data from other files will be averaged with data from this file
        if dest_fname!=source_fnames[0]:
            copy(source_fnames[0], dest_fname)

        for fname in source_fnames:
            with h5py.File(dest_fname, 'r+') as dest_file, h5py.File(fname, 'r') as file:
                dest_data = dest_file['data']
                data = file['data']
                for key in dest_data:
                    dest_data_column = np.array(dest_data[key][:])
                    data_column = np.array(data[key][:])
                    avg_column = np.average(np.vstack((dest_data_column, data_column)), axis=0)
                    dest_file['data'][key][:] = avg_column

        # with h5py.File(source_fnames[0], 'r') as file:
        #     calibration = file['calibration'][()].decode()
        #     settings = file['settings'][()].decode()
        # data = open(source_fnames[0]+"::/data")
        # with h5py.File(dest_fname, 'w') as file:
        #     file.create_dataset('calibration', data=calibration)
        #     file.create_dataset('settings', data=settings)
        #     data_fgroup = file.create_group('data')
        #     for key in data:
        #         data_fgroup.create_dataset(key, data=data[key][:])

    def display_rate_button_pressed(self):
        smooth_factor = int(self.smoothInput.text())
        if self.expFilesTable.count()>1:
            warning = "The average of all data files will be calculated.\nProceed?"
            buttonReply = YesCancelWindow(warning).exec()
            if buttonReply == qt.QMessageBox.Yes:
                avg_fname = self.average_exp_data()
                if not avg_fname:
                    return
            else:
                self.update_GUI()
                return
        if self.emptyFilesTable.count()>1:
            warning = "The average of all reference data will be calculated.\nProceed?"
            buttonReply = YesCancelWindow(warning).exec()
            if buttonReply == qt.QMessageBox.Yes:
                avg_fname = self.average_empty_data()
                if not avg_fname:
                    return
            else:
                self.update_GUI()
                return
        
        self.load_initial_data()
        self.exp_data['rate'] = self.calculate_temp_gradient(self.exp_data['temp'], 
                                                    self.exp_data['time'], 
                                                    smooth_factor)
        self.empty_data['rate'] = self.calculate_temp_gradient(self.empty_data['temp'], 
                                                    self.empty_data['time'], 
                                                    smooth_factor)
        self.update_plot_after_display_rate()
        
    def find_iso(self):
        pass
        # TODO: make a proper algorythm to find isotherms. Probably use the 2nd or 3rd derivative

        # smooth_factor = int(self.smoothInput.text())
        # firstTempGradient = self.calculate_temp_gradient(self.empty_data['temp'], 
        #                                             self.empty_data['time'], 
        #                                             smooth_factor)

        # secondTempGradient = self.calculate_temp_gradient(self.empty_data['rate'], 
        #                                                 self.empty_data['time'], 
        #                                                 smooth_factor)

        # thirdTempGradient = self.calculate_temp_gradient(secondTempGradient, 
        #                                                 self.empty_data['time'], 
        #                                                 smooth_factor)

        # self.procFastHeatGraph.resultPlot.clear()
        # self.procFastHeatGraph.resultPlot.addCurve(self.empty_data['time'], firstTempGradient, 
        #                                             legend='first',
        #                                             color = self.procFastHeatGraph.curveColors['gray'])

        # self.procFastHeatGraph.resultPlot.addCurve(self.empty_data['time'], secondTempGradient, 
        #                                             legend='second',
        #                                             color = self.procFastHeatGraph.curveColors['red'])
        # self.procFastHeatGraph.resultPlot.addCurve(self.empty_data['time'], thirdTempGradient, 
        #                                             legend='third',
        #                                             color = self.procFastHeatGraph.curveColors['blue'])

    def calculate_manual_button_pressed(self):
        calib_coeff_1 = float(self.rcoeff1Input.text())
        calib_coeff_2 = float(self.rcoeff2Input.text())
        calib_coeff_3 = float(self.rcoeff3Input.text())

        isoBeginIdx = np.abs(self.empty_data['time'] - int(self.isoBeginInput.value())).argmin() 
        isoEndIdx = np.abs(self.empty_data['time'] - int(self.isoEndInput.value())).argmin()
        _, empty_G, empty_G_temp, _ = self.calculate_heat_exch_coeff(
                                        calib_coeff_1, calib_coeff_2, calib_coeff_3,
                                        self.empty_data['Uref'], self.empty_data['Thtr'], 
                                        self.empty_data['temp'], self.empty_data['rate'], 
                                        isoBeginIdx, isoEndIdx)
        dT = self.exp_data['temp']-self.empty_data['temp']
        
        self.exp_data['exp_P'] = self.calculate_P(dT, empty_G, empty_G_temp, self.empty_data['temp'])

        # save calculated data to file. the distanation file is selected depending
        # on saveFileOption checkbox
        source_file = self.expFilesTable.item(0).text()
        if self.saveFileOption.checkState() == 2:         # 2 = checked
            dest_file = source_file
        else:
            source_fname = self.expFilesTable.item(0).text().split('/')[-1].split('.')[0]
            dest_file = qt.QFileDialog().getSaveFileName(self, "Save processed file as...", 
                                            source_fname+'_p.h5', 
                                            "*h5 files (*.h5)")[0]
        if dest_file:
            self.save_processed_file(source_file, dest_file, 
                                    {'exp_P' : self.exp_data['exp_P'], 
                                    'empty_G' : empty_G, 
                                    'empty_G_temp': empty_G_temp,
                                    'empty_temp': self.empty_data['temp'],
                                    'dT': dT})
        self.update_plot_after_calc_button_pressed()

    def calculate_auto_button_pressed(self):
        calib_coeff_1 = float(self.rcoeff1Input.text())
        calib_coeff_2 = float(self.rcoeff2Input.text())
        calib_coeff_3 = float(self.rcoeff3Input.text())
     
        if self.autoOption1Selector.currentText() == "all experiment files with one reference file":
            if self.emptyFilesTable.count()>1:
                ErrorWindow("Unable to proceed. Leave only one reference file and try again.")
                return
        
        if self.autoOption1Selector.currentText() == "each experiment file with own reference file":
            if self.emptyFilesTable.count()!=self.expFilesTable.count():
                ErrorWindow("Unable to proceed. The amount of experiment and reference files are different.")
                return
            
        if self.autoOption1Selector.currentText() == "each experiment file with auto-guess reference":
            MessageWindow("Still under development...")
            return

        if self.autoOption2Selector.currentText() == "heat exchange auto calculation":
            MessageWindow("Still under development...")
            return
        if self.autoOption2Selector.currentText() == "heat exchange constant value":
            pass
        
    def save_processed_file(self, source_file: str, dest_file: str, data_to_save: dict):
        if dest_file!=source_file:
            copy(source_file, dest_file)
        with h5py.File(dest_file, 'r+') as file:
            dest_data = file['data']
            for array_name, array in data_to_save.items():
                if array_name in dest_data.keys():
                    del dest_data[array_name]
                dest_data.create_dataset(array_name, data = array)

    # functions to calculate heat exhange coefficient, power, dT, etc. 
    def calculate_temp_gradient(self, temp_array, time_array, smooth_factor):
        temp_smooth = filters.savitsky_golay(temp_array, smooth_factor)
        dt = time_array[1]-time_array[0]
        return np.gradient(temp_smooth, dt)

    def calculate_heat_exch_coeff(self, calib_coeff_1, calib_coeff_2, calib_coeff_3,
                                    Uhtr, Thtr, temp, rate, 
                                    end_heating, start_cooling):
        empty_P = self.calculate_empty_P(calib_coeff_1, calib_coeff_2, calib_coeff_3, 
                                        Uhtr, Thtr)
        empty_G = np.array([None for i in range(end_heating)], dtype=np.float32)
        empty_GdT = np.array([None for i in range(end_heating)], dtype=np.float32)
        empty_G_temp = np.linspace(temp[0], temp[end_heating], end_heating)
        
        empty_temp_heating = np.array([9999.0 for i in range(len(temp))])
        empty_temp_heating[:end_heating] = temp[:end_heating]
        empty_temp_cooling = np.array([9999.0 for i in range(len(temp))])
        empty_temp_cooling[start_cooling:] = temp[start_cooling:]

        for i in range(len(empty_G_temp)):
            pos1 = (np.abs(empty_temp_heating - empty_G_temp[i]).argmin())
            pos2 = (np.abs(empty_temp_cooling - empty_G_temp[i]).argmin())
            empty_GdT[i] = (abs(rate[pos2])/(abs(rate[pos1])+abs(rate[pos2])))*\
                            abs(empty_P[pos1]-empty_P[pos2])+empty_P[pos2]
            empty_G[i] = empty_GdT[i]/(empty_G_temp[i]-empty_G_temp[0])
        empty_G[0]=0

        return empty_P, empty_G, empty_G_temp, empty_GdT
        
    def calculate_empty_P(self, calib_coeff_1, calib_coeff_2, calib_coeff_3, 
                            empty_Uhtr, empty_Thtr):
        empty_Rg = -0.5*calib_coeff_2/calib_coeff_3 - \
                    np.sqrt((calib_coeff_2**2-4*calib_coeff_3*(calib_coeff_1-empty_Thtr))/4/calib_coeff_3**2)
        empty_P = empty_Uhtr**2/empty_Rg
        return empty_P

    def calculate_P(self, dT, empty_G, empty_G_temp, empty_temp):
        exp_P = np.array([None for i in range(len(empty_temp))], dtype=np.float32)
        for i in range(len(empty_temp)):
            exp_P[i] = dT[i] * empty_G[np.abs(empty_G_temp-empty_temp[i]).argmin()]
        return exp_P

    # functions to update UI elements

    def update_GUI(self):
        self.groupBoxesStateInstance.start()
        self.heatExchFieldsStateInstance.start()

    def update_plot_after_add_remove(self):
        self.procFastHeatGraph.clear()
        empty_paths = [self.emptyFilesTable.item(x).text() for x in range(self.emptyFilesTable.count())]
        if empty_paths:
            for path in empty_paths:
                data = open(path+"::/data")
                self.procFastHeatGraph.addCurve(data['time'], data['temp'], 
                                                            legend=path.split('/')[-1].split('.')[0],
                                                            color = self.procFastHeatGraph.curveColors['gray'])
                data.close()
        exp_paths = [self.expFilesTable.item(x).text() for x in range(self.expFilesTable.count())]
        if exp_paths:
            for path in exp_paths:
                data = open(path+"::/data")
                self.procFastHeatGraph.addCurve(data['time'], data['temp'], 
                                                            legend=path.split('/')[-1].split('.')[0],
                                                            color = self.procFastHeatGraph.curveColors['red'])
                data.close()
    
    def update_calib_fields_after_add_remove(self):
        exp_paths = [self.expFilesTable.item(x).text() for x in range(self.expFilesTable.count())]
        if exp_paths:
            calibration_ds = open(exp_paths[0]+"::/calibration")
            self.calibration = json.loads(calibration_ds[()].decode())
            self.rcoeff1Input.setText(str(self.calibration['thtr0']))
            self.rcoeff2Input.setText(str(self.calibration['thtr1']))
            self.rcoeff3Input.setText(str(self.calibration['thtr2']))
            rgRhRatio = round(self.calibration['rghtr']/self.calibration['rhtr'], 3)
            self.rgRhRatioInput.setText(str(rgRhRatio))
            calibration_ds.close()

    def update_plot_after_display_rate(self):
        self.procFastHeatGraph.clear()
        self.procFastHeatGraph.addCurve(self.empty_data['time'], self.empty_data['rate'], 
                                                    legend='',
                                                    color = self.procFastHeatGraph.curveColors['red'])

        # TODO: add roi after auto-guess or to the center of graph
        self.procFastHeatGraph.setRoi(400, 600)
        self.isoBeginInput.setValue(400)
        self.isoEndInput.setValue(600)

    def update_plot_after_calc_button_pressed(self):
        self.procFastHeatGraph.clear()
        # need to remove roi after selection of isotherm to use new roi for baseline subtraction
        self.procFastHeatGraph.removeRoi()

        #TODO: change middle point after introducing saving of temp program to file.
        # make proper segments devide to get only heating and only cooling
        middle = int(len(self.empty_data['temp'])/2)

        self.procFastHeatGraph.addCurve(self.empty_data['temp'][:middle], 
                                        self.exp_data['exp_P'][:middle], 
                                        legend='empty power heating',
                                        color = self.procFastHeatGraph.curveColors['lightred'])
        self.procFastHeatGraph.addCurve(self.exp_data['temp'][:middle],
                                        self.exp_data['exp_P'][:middle], 
                                        legend='exp power heating',
                                        color = self.procFastHeatGraph.curveColors['red'])
        self.procFastHeatGraph.addCurve(self.empty_data['temp'][middle:],
                                        self.exp_data['exp_P'][middle:], 
                                        legend='empty power cooling',
                                        color = self.procFastHeatGraph.curveColors['lightblue'])
        self.procFastHeatGraph.addCurve(self.exp_data['temp'][middle:],
                                        self.exp_data['exp_P'][middle:], 
                                        legend='exp power cooling',
                                        color = self.procFastHeatGraph.curveColors['blue'])


    # functions to connect roi selection with selectboxes for iso
    def update_graph_roi_min(self):
        cursor = self.isoBeginInput.value()
        self.isoEndInput.setMinimum(cursor)
        self.procFastHeatGraph.roi.setMin(cursor)

    def update_graph_roi_max(self):
        cursor = self.isoEndInput.value()
        self.isoBeginInput.setMaximum(cursor)
        self.procFastHeatGraph.roi.setMax(cursor)

    def update_iso_inputs(self, ddict=None):
        if ddict['event'] == "markerMoved":
            if ddict['button'] == "left":
                cursor1, cursor2 = self.procFastHeatGraph.roi.getRange()
                self.isoEndInput.setValue(int(cursor2))
                self.isoBeginInput.setValue(int(cursor1))
        

class GroupBoxesState(qt.QThread):
    state = qt.pyqtSignal(bool)
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
    def run(self):
        if self.mainWindow.expFilesTable.count()>0 and self.mainWindow.emptyFilesTable.count()>0:
            self.state.emit(True)
        else:
            self.state.emit(False)

class HeatExchFieldsState(qt.QThread):
    state = qt.pyqtSignal(bool)
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
    def run(self):
        if self.mainWindow.autoOption2Selector.currentText()=="heat exchange constant value":
            self.state.emit(True)
        else:
            self.state.emit(False)


if __name__ == "__main__":
    import sys
    app = qt.QApplication(sys.argv)
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = procFastHeatWidget()
    example.show()
    sys.exit(app.exec())