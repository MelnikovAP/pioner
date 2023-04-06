import sys
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import json
from enum import Enum
from typing import List


class SetProg(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tab1 = ProfileWidget("Channel 0")
        self.tab1.setObjectName("Tab 0")
        self.tab2 = ProfileWidget("Channel 1")
        self.tab2.setObjectName("Tab 1")
        self.tab3 = ProfileWidget("Channel 2")
        self.tab3.setObjectName("Tab 2")
        self.tab4 = ProfileWidget("Channel 3")
        self.tab4.setObjectName("Tab 3")

        # Creating a vertical layout to place tabs
        self.rightLayout = QVBoxLayout()
        # Create the main tab widget
        self.mainTabWidget = QTabWidget()
        self.controlTab = QWidget()

        # Adding the main widget to the vertical layout
        self.mainTabWidget.addTab(self.tab1, "Channel 0")
        self.mainTabWidget.addTab(self.tab2, "Channel 1")
        self.mainTabWidget.addTab(self.tab3, "Channel 2")
        self.mainTabWidget.addTab(self.tab4, "Channel 3")

        self.rightLayout.addWidget(self.mainTabWidget)

        # Creating a vertical layout to place control elements
        self.layout = QVBoxLayout()

        # Adding the vertical layout with tabs to the vertical layout
        self.layout.addLayout(self.rightLayout)
        self.setLayout(self.layout)

    # Function for getting a dictionary of profile data from tabs
    def get_main_dict(self):
        profiles_data = {}
        # add dict from all tabs
        for i in range(self.mainTabWidget.count()):
            tab = self.mainTabWidget.widget(i)
            profiles_data[i] = tab.get_dict()
        print(profiles_data)
        return profiles_data


class ProfileWidget(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent=parent)
        self.name = name

        # Create the layout for the table and buttons
        layer2 = QHBoxLayout()
        layer3 = QVBoxLayout()

        # Create a table widget and set its properties
        self.tableWidget = QTableWidget(self)
        self.tableWidget.setColumnCount(3)
        self.tableWidget.setRowCount(0)
        self.tableWidget.horizontalHeader().setVisible(False)
        self.tableWidget.setColumnWidth(0, 110)
        self.tableWidget.setColumnWidth(1, 260)
        self.tableWidget.setColumnWidth(2, 120)

        # Create buttons and a combobox
        buttonARM = QPushButton('ARM')
        buttonADD = QPushButton('+')
        buttonSAVE = QPushButton('SAVE')
        buttonLOAD = QPushButton('LOAD')
        buttonDEL1s = QPushButton('-')
        self.typecbox = QComboBox()
        self.typecbox.addItems(["°C", "V"])

        # Create labels for the table columns
        typelabel = QLabel('Value type:')
        labeltime = QLabel()
        labelval = QLabel()
        labeltime.setText('Time')
        labelval.setText("Value")

        # Add widgets to the layout
        layer3.addWidget(self.tableWidget, 0)
        layer2.addWidget(buttonADD, 0)
        layer2.addWidget(buttonDEL1s, 0)
        layer2.addWidget(buttonSAVE, 0)
        layer2.addWidget(buttonLOAD, 0)
        layer2.addWidget(typelabel, 0)
        layer2.addWidget(self.typecbox, 0)
        layer2.addWidget(buttonARM, 0)

        # Set the size of the add and delete buttons
        buttonADD.setFixedSize(60, 25)
        buttonDEL1s.setFixedSize(60, 25)

        # Create the main layout for the widget and add the sub-layouts
        self.layout = QVBoxLayout()
        self.layout.addLayout(layer3)
        self.layout.addLayout(layer2)
        self.setLayout(self.layout)

        # Connect button signals to their corresponding functions

        buttonADD.clicked.connect(lambda: self.add_layer(self.tableWidget.rowCount()))
        buttonDEL1s.clicked.connect(lambda: self.mass_del())
        buttonARM.clicked.connect(lambda: self.parent().parent().parent().get_main_dict())
        buttonSAVE.clicked.connect(lambda: self.saving_procedure())
        buttonLOAD.clicked.connect(lambda: self.table_from_file())
        self.typecbox.currentIndexChanged.connect(self.change_type_value)

    def change_type_value(self):
        for i in range(self.tableWidget.rowCount()):
            row_widget1 = self.tableWidget.cellWidget(i, 1).layout()
            row_widget2 = self.tableWidget.cellWidget(i, 2).layout()
            for k in range(row_widget1.count()):
                if row_widget1.itemAt(k).widget().text() == "°C":

                    row_widget1.itemAt(k).widget().setText('V')
                elif row_widget1.itemAt(k).widget().text() == 'V':

                    row_widget1.itemAt(k).widget().setText("°C")
            for k in range(row_widget2.count()):
                if row_widget2.itemAt(k).widget().text() in ["°C/min", "°C/ms", "°C/s"]:
                    row_widget2.itemAt(k).widget().setText('V/' + row_widget2.itemAt(k).widget().text().split('/')[1])
                elif row_widget2.itemAt(k).widget().text() in ["V/min", "V/ms", "V/s"]:

                    row_widget2.itemAt(k).widget().setText("°C/" + row_widget2.itemAt(k).widget().text().split('/')[1])
            self.tableWidget.cellWidget(i, 1).setLayout(row_widget1)
            self.tableWidget.cellWidget(i, 2).setLayout(row_widget2)

    def saving_procedure(self):
        # Create empty dictionaries to store table data and overall information
        tab_dict = {}
        table_dict = {}

        # Get the unit type from the combo box and add it to the table dictionary
        table_dict['unit'] = self.typecbox.currentText()

        # Check if the table is empty or not
        if self.tableWidget.rowCount() != 0:
            # Loop through each row of the table and create a dictionary for that row's data
            for row in range(self.tableWidget.rowCount()):
                row_dict = {}

                # Get the mode type for this row and add it to the row dictionary
                row_dict['mode_type'] = self.tableWidget.cellWidget(row, 0).text()

                # For each mode type, get the appropriate values from the table and add them to the row dictionary
                if row_dict['mode_type'] == "Isotherm":
                    row_dict['from_value'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(1).widget().text()
                    row_dict['time_value'] = self.tableWidget.cellWidget(row, 2).layout().itemAt(1).widget().text()
                    row_dict['time_type'] = self.tableWidget.cellWidget(row, 2).layout().itemAt(2).widget().text()
                if row_dict['mode_type'] == "Ramp":
                    row_dict['from_value'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(1).widget().text()
                    row_dict['to_value'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(4).widget().text()
                    row_dict['rate_value'] = self.tableWidget.cellWidget(row, 2).layout().itemAt(1).widget().text()
                    row_dict['rate_type'] = self.tableWidget.cellWidget(row, 2).layout().itemAt(2).widget().text()
                    row_dict['to_value'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(4).widget().text()
                if row_dict['mode_type'] == "Sine Segment":
                    row_dict['Ampl'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(1).widget().text()
                    row_dict['Freq'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(4).widget().text()
                    row_dict['Offs'] = self.tableWidget.cellWidget(row, 1).layout().itemAt(6).widget().text()
                    row_dict['time_value'] = self.tableWidget.cellWidget(row, 2).layout().itemAt(1).widget().text()
                    row_dict['time_type'] = self.tableWidget.cellWidget(row, 2).layout().itemAt(2).widget().text()

                    # Add this row's dictionary to the overall table dictionary
                table_dict[row] = row_dict

            # Add the table dictionary to the overall dictionary
            tab_dict['rowdata'] = table_dict

        # Set options for the file dialog
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog

        # Open the file dialog to get the file path to save to
        file_path, _ = QFileDialog.getSaveFileName(self, "New File", "", "JSON Files (*.json)", options=options)

        # If a file path was selected, save the data to that file
        if file_path:
            # If the file path does not end in .json, add it
            if not file_path.endswith('.json'):
                file_path += '.json'

            with open(file_path, 'w') as f:
                json.dump(tab_dict, f, indent=4)

    def table_from_file(self):
        # Define options for file dialog
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog  # add the QFileDialog.DontUseNativeDialog option to options
        # Open file dialog and get file path
        file_path, _ = QFileDialog.getOpenFileName(self, "Open File", "", "JSON Files (*.json)",
                                                   options=options)  # open a file dialog and get the selected file path

        if file_path:
            with open(file_path, 'r') as f:
                data = json.load(f)
        else:
            return

        rows_data = data['rowdata']
        self.tableWidget.clear()
        self.tableWidget.setRowCount(0)
        # Iterate through the keys in rows_data
        row_data = {}
        for key in rows_data.keys():
            if key == 'unit':
                typeval1 = rows_data['unit']
                typeval2 = typeval1

                print(typeval1)
                continue
            else:
                row_data = rows_data[key]

            mode_type = row_data['mode_type']

            if mode_type == "Isotherm":
                val1 = row_data['from_value']
                time = row_data['time_value']
                typetime = row_data['time_type']
            if mode_type == "Ramp":
                val1 = row_data['from_value']
                val2 = row_data['to_value']
                time = row_data['rate_value']
                typetime = row_data['rate_type']
            if mode_type == "Sine Segment":
                val1 = row_data['Ampl']
                val2 = row_data['Freq']
                val3 = row_data['Offs']
                time = row_data['time_value']
                typetime = row_data['time_type']

            row_number = self.tableWidget.rowCount()
            self.tableWidget.insertRow(row_number)
            self.typecbox.setCurrentText(typeval1)

            buttrow = QPushButton(row_data['mode_type'])
            buttrow.setObjectName("but" + str(row_number))
            buttrow.clicked.connect(lambda checked, x=row_number: self.add_layer(x,False))
            self.tableWidget.setCellWidget(row_number, 0, buttrow)

            flabel = QLabel("Ampl: " if mode_type == "Sine Segment" else "From:")
            spineditval1 = QLabel(str(val1))
            labelval1 = QLabel(typeval1 if mode_type != "Sine Segment" else "")
            hlayer1 = QHBoxLayout()
            hlayer1.addWidget(flabel)
            hlayer1.addWidget(spineditval1)
            hlayer1.addWidget(labelval1)
            wid1 = QWidget()
            if mode_type == "Ramp":
                tLabel = QLabel("To: ")
                spineditval2 = QLabel(val2)
                labelval2 = QLabel(typeval2)
                hlayer1.addWidget(tLabel)
                hlayer1.addWidget(spineditval2)
                hlayer1.addWidget(labelval2)
                wid1.setLayout(hlayer1)
            if mode_type == "Sine Segment":
                tLabel = QLabel("Freq: ")
                oLabel = QLabel("Offs: ")
                spineditval2 = QLabel(val2)
                spineditval3 = QLabel(val3)
                labelval2 = QLabel()
                hlayer1.addWidget(tLabel)
                hlayer1.addWidget(spineditval2)
                hlayer1.addWidget(oLabel)
                hlayer1.addWidget(spineditval3)
                hlayer1.addWidget(labelval2)
                wid1.setLayout(hlayer1)
            self.tableWidget.setCellWidget(row_number, 1, wid1)
            wid1.setLayout(hlayer1)

            spineditduration = QLabel(
                "Duration: " if mode_type == "Isotherm" or mode_type == "Sine Segment" else "Rate: ")
            labeltime = QLabel(typetime)
            labelvaltime = QLabel(time)
            hlayer3 = QHBoxLayout()
            hlayer3.addWidget(spineditduration)
            hlayer3.addWidget(labelvaltime)
            hlayer3.addWidget(labeltime)
            wid2 = QWidget()
            wid2.setLayout(hlayer3)
            self.tableWidget.setCellWidget(row_number, 2, wid2)

            # self.typecbox.setEnabled(False)

    def add_layer(self, x: int, b = True):

        dialog = InputDialog1(self.typecbox.currentText())
        self.parent().setWindowModality(Qt.WindowModal)
        if x == self.tableWidget.rowCount():
            row_number = self.tableWidget.rowCount()

        else:

            row_number = x
            mode_type = self.tableWidget.cellWidget(row_number, 0).text()

            if mode_type == "Isotherm":
                from_value = self.tableWidget.cellWidget(row_number, 1).layout().itemAt(1).widget().text()
                time_value = self.tableWidget.cellWidget(row_number, 2).layout().itemAt(1).widget().text()
                time_type = self.tableWidget.cellWidget(row_number, 2).layout().itemAt(2).widget().text()
                dialog.set_values(from_value, time_value, mode_type, time_type)
            if mode_type == "Ramp":
                from_value = self.tableWidget.cellWidget(row_number, 1).layout().itemAt(1).widget().text()
                to_value = self.tableWidget.cellWidget(row_number, 1).layout().itemAt(4).widget().text()
                time_value = self.tableWidget.cellWidget(row_number, 2).layout().itemAt(1).widget().text()
                time_type = self.tableWidget.cellWidget(row_number, 2).layout().itemAt(2).widget().text().split('/')[1]
                dialog.set_values(from_value, time_value, mode_type, time_type, to_value)
            if mode_type == "Sine Segment":
                Ampl = self.tableWidget.cellWidget(row_number, 1).layout().itemAt(1).widget().text()
                Freq = self.tableWidget.cellWidget(row_number, 1).layout().itemAt(4).widget().text()
                Offs = self.tableWidget.cellWidget(row_number, 1).layout().itemAt(6).widget().text()
                time_value = self.tableWidget.cellWidget(row_number, 2).layout().itemAt(1).widget().text()
                time_type = self.tableWidget.cellWidget(row_number, 2).layout().itemAt(2).widget().text()
                dialog.set_values(Ampl, time_value, mode_type, time_type, Freq, Offs)



        if dialog.exec_() == QDialog.Accepted:
            self.tableWidget.insertRow(row_number)
            if b != True:
                self.tableWidget.removeRow(row_number+1)
            mode_type = dialog.type_combo.currentText()
            # Create and set the button widget
            buttrow = QPushButton(mode_type)
            buttrow.setObjectName("but" + str(row_number))
            buttrow.clicked.connect(lambda checked, x=row_number: self.add_layer(x, False))
            self.tableWidget.setCellWidget(row_number, 0, buttrow)
            # Create and set the first value widget
            typeval1 = dialog.val_cb1.text()
            val1 = dialog.edit_val1.text()

            flabel = QLabel("Ampl: " if mode_type == "Sine Segment" else "From:")
            spineditval1 = QLabel(str(val1))
            labelval1 = QLabel(typeval1 if mode_type != "Sine Segment" else "")
            hlayer1 = QHBoxLayout()
            hlayer1.addWidget(flabel)
            hlayer1.addWidget(spineditval1)
            hlayer1.addWidget(labelval1)
            wid1 = QWidget()
            if mode_type == "Ramp":
                typeval2 = dialog.val_cb2.text()
                val2 = dialog.edit_val2.text()

                tLabel = QLabel("To: ")
                spineditval2 = QLabel(val2)
                labelval2 = QLabel(typeval2)
                hlayer1.addWidget(tLabel)
                hlayer1.addWidget(spineditval2)
                hlayer1.addWidget(labelval2)
                wid1.setLayout(hlayer1)
            if mode_type == "Sine Segment":
                typeval2 = ""
                typeval1 = ""
                val2 = dialog.edit_val2.text()
                val3 = dialog.edit_val4.text()

                tLabel = QLabel("Freq: ")
                oLabel = QLabel("Offs: ")
                spineditval2 = QLabel(val2)
                spineditval3 = QLabel(val3)
                labelval2 = QLabel(typeval2)
                hlayer1.addWidget(tLabel)
                hlayer1.addWidget(spineditval2)
                hlayer1.addWidget(oLabel)
                hlayer1.addWidget(spineditval3)
                hlayer1.addWidget(labelval2)
                wid1.setLayout(hlayer1)
            self.tableWidget.setCellWidget(row_number, 1, wid1)
            self.tableWidget.cellDoubleClicked.connect(lambda checked, x=row_number: self.add_layer(x, False))
            wid1.setLayout(hlayer1)
            # Create and set the time widget
            typetime = dialog.val_cb3.currentText()
            time = dialog.edit_val3.text()

            spineditduration = QLabel(
                "Duration: " if mode_type == "Isotherm" or mode_type == "Sine Segment" else "Rate: ")
            labeltime = QLabel(self.typecbox.currentText() + "/" + typetime if mode_type == "Ramp" else typetime)
            labelvaltime = QLabel(time)
            hlayer3 = QHBoxLayout()
            hlayer3.addWidget(spineditduration)
            hlayer3.addWidget(labelvaltime)
            hlayer3.addWidget(labeltime)
            wid2 = QWidget()
            wid2.setLayout(hlayer3)

            self.tableWidget.setCellWidget(row_number, 2, wid2)
            self.tableWidget.cellClicked
        else:
            if b == True:
                self.tableWidget.removeRow(x)

    # self.typecbox.setEnabled(False)



    def mass_del(self):
        # Function to delete selected rows from the table widget
        row_number = self.tableWidget.rowCount()
        # If there is a selection in the table widget, delete the selected rows
        if self.tableWidget.selectionModel().hasSelection():
            # Create an empty list to store the selected indices
            index_list = []

            # Loop through the selected rows and add their indices to the index list
            for model_index in self.tableWidget.selectionModel().selectedRows():
                index = QPersistentModelIndex(model_index)
                index_list.append(index)

            # Loop through the index list and remove the corresponding rows from the table widget
            for index in index_list:
                self.tableWidget.removeRow(index.row())
        # If there is no selection, remove the last row in the table widget
        else:
            self.tableWidget.removeRow(row_number - 1)

        # Loop through the rows of the table widget and update the object names of the buttons
        for i in range(row_number):
            if self.tableWidget.cellWidget(i, 0) is not None:
                self.tableWidget.cellWidget(i, 0).setObjectName("but" + str(i))
                self.tableWidget.cellWidget(i, 0).clicked.disconnect()
                self.tableWidget.cellWidget(i, 0).clicked.connect(lambda checked, x = i : self.add_layer(x, False))

        # If the table widget is now empty, enable the typecbox combo box
        if self.tableWidget.rowCount() == 0:
            self.typecbox.setEnabled(True)

    def get_dict(self):
        # Get the currently selected type from a combo box
        typeval = self.typecbox.currentText()

        # Create an empty dictionary to store data
        data = {}

        # Initialize variables to be used in the loop
        stmoment = 0.
        duration = 0.
        endmoment = 0.
        stval = 0.
        endval = 0.
        ampl = 0.
        freq = 0.
        offs = 0.
        segments = []

        # Iterate through the rows of a table widget
        for i in range(self.tableWidget.rowCount()):
            # Calculate start and end moments for the current segment
            stmoment = stmoment + duration
            endmoment = stmoment + duration

            # Get the type of the current segment
            seg_type = self.tableWidget.cellWidget(i, 0).text()

            # Get the units for the duration of the current segment
            typewid = self.tableWidget.cellWidget(i, 0).text()
            if seg_type == "Ramp":
                typetime = self.tableWidget.cellWidget(i, 2).layout().itemAt(2).widget().text().split("/")[1].strip()
            else:
                typetime = self.tableWidget.cellWidget(i, 2).layout().itemAt(
                    2).widget().text()  # .split("/" if typewid =="Ramp" else "")

            # Convert the duration to seconds based on the units
            if typetime == "s":
                duration = float(duration)
            if typetime == "ms":
                duration = float(duration) / 1000
            if typetime == "min":
                duration = float(duration) * 60

                # Create the appropriate segment based on the segment type
            if seg_type == "Isotherm":
                stval = float(self.tableWidget.cellWidget(i, 1).layout().itemAt(1).widget().text())
                endmoment = stmoment + duration
                segment = IsoSegment(stmoment, endmoment, stval)
                segments.append(segment)

            if seg_type == "Ramp":
                stval = float(self.tableWidget.cellWidget(i, 1).layout().itemAt(1).widget().text())
                endval = float(self.tableWidget.cellWidget(i, 1).layout().itemAt(4).widget().text())
                duration = (endval - stval) / duration
                endmoment = stmoment + duration
                segment = RampSegment(stmoment, endmoment, stval, endval)
                segments.append(segment)

            if seg_type == "Sine Segment":
                ampl = float(self.tableWidget.cellWidget(i, 1).layout().itemAt(1).widget().text())
                freq = float(self.tableWidget.cellWidget(i, 1).layout().itemAt(4).widget().text())
                offs = float(self.tableWidget.cellWidget(i, 1).layout().itemAt(6).widget().text())
                endmoment = stmoment + duration
                segment = SineSegment(stmoment, endmoment, endval, ampl, freq, offs)
                segments.append(segment)

        # Determine the data type based on the selected type in the combo box
        if typeval == "V":
            data_type = DataType.VOLT
        else:
            data_type = DataType.TEMP

        # Create a ProfileData object using the collected data
        data = ProfileData(data_type, segments)

        # Return the created ProfileData object
        return data


class InputDialog1(QDialog):
    def __init__(self, type: str, parent=None):
        QDialog.__init__(self, parent)
        reg_ex = QRegExp("[0-9.]*")

        # create a validator
        validator = QRegExpValidator(reg_ex)

        self.setWindowTitle("Add Option")
        self.val_cb1 = QLabel()
        self.val_cb1.setText(type)
        self.val_cb2 = QLabel()
        self.val_cb2.setText(type)
        self.rate = QLabel()
        self.rate.setText(type + "/")
        self.val_cb3 = QComboBox()
        self.val_cb3.addItems(['s', 'ms', 'min'])
        self.val_cb3.setMinimumSize(80, 25)
        self.horlayout0 = QHBoxLayout()
        self.horlayout1 = QHBoxLayout()
        self.edit_val1 = QLineEdit()
        self.edit_val1.setValidator(validator)
        self.edit_val2 = QLineEdit()
        self.edit_val2.setValidator(validator)
        self.edit_val4 = QLineEdit()  # offset
        self.edit_val4.setValidator(validator)

        self.edit_val3 = QLineEdit()
        self.edit_val3.setValidator(validator)
        self.label1 = QLabel("val1")
        self.label2 = QLabel("val2")
        self.label4 = QLabel("Offset")
        self.label3 = QLabel("Duration")
        self.type_label = QLabel("Choose type")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Isotherm", "Ramp", "Sine Segment"])
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept1)
        self.button_box.rejected.connect(self.reject)
        layer1 = QVBoxLayout()
        vlayer1 = QVBoxLayout()
        vlayer2 = QVBoxLayout()
        vlayer3 = QVBoxLayout()
        vlayer4 = QVBoxLayout()
        vlayer5 = QVBoxLayout()
        hlayer1 = QHBoxLayout()
        hlayer2 = QHBoxLayout()
        hlayer3 = QHBoxLayout()

        self.layout = QVBoxLayout()

        vlayer1.addWidget(self.type_label)
        vlayer1.addWidget(self.type_combo)
        vlayer2.addWidget(self.label1)
        hlayer1.addWidget(self.edit_val1)
        hlayer1.addWidget(self.val_cb1)
        vlayer2.addLayout(hlayer1)
        vlayer3.addWidget(self.label2)
        hlayer2.addWidget(self.edit_val2)
        hlayer2.addWidget(self.val_cb2)
        vlayer3.addLayout(hlayer2)
        vlayer4.addWidget(self.label4)
        vlayer4.addWidget(self.edit_val4)
        vlayer5.addWidget(self.label3)
        hlayer3.addWidget(self.edit_val3)
        hlayer3.addWidget(self.rate)
        hlayer3.addWidget(self.val_cb3)
        vlayer5.addLayout(hlayer3)
        self.horlayout0.addLayout(vlayer1)
        self.horlayout0.addLayout(vlayer2)
        self.horlayout0.addLayout(vlayer3)
        self.horlayout0.addLayout(vlayer4)
        self.horlayout0.addLayout(vlayer5)

        self.layout.addLayout(self.horlayout0)

        layer1.addLayout(self.layout)
        layer1.addWidget(self.button_box)
        self.setLayout(layer1)
        self.change_type()
        self.type_combo.currentTextChanged.connect(self.change_type)

    def set_values(self, val1, val3, type_mode, duration_unit, val2='', val4=''):
        index = self.type_combo.findText(type_mode)
        self.type_combo.setCurrentIndex(index)
        self.change_type()

        self.edit_val1.setText(str(val1))
        self.edit_val2.setText(str(val2))
        self.edit_val3.setText(str(val3))
        self.edit_val4.setText(str(val4))

        index2 = self.val_cb3.findText(duration_unit)
        self.val_cb3.setCurrentIndex(index2)

    def text_take(self, type_mode: str, arg: list):
        index = self.type_combo.findText(type_mode)
        self.type_combo.setCurrentIndex(index)
        self.change_type()
        if type_mode == "Isotherm":
            self.edit_val1.setText(arg[1])
            self.edit_val3.setText(arg[2])
            index2 = self.val_cb3.findText(arg[3])
            self.val_cb3.setCurrentIndex(index2)
        if type_mode == "Ramp":
            self.edit_val1.setText(arg[1])
            self.edit_val2.setText(arg[2])
            self.edit_val3.setText(arg[3])
            index2 = self.val_cb3.findText(arg[4])
            self.val_cb3.setCurrentIndex(index2)
        if type_mode == "Sine Segment":
            self.edit_val1.setText(arg[1])
            self.edit_val2.setText(arg[2])
            self.edit_val3.setText(arg[4])
            self.edit_val3.setText(arg[3])
            index2 = self.val_cb3.findText(arg[5])
            self.val_cb3.setCurrentIndex(index2)

    def change_type(self):
        if self.type_combo.currentText() == "Isotherm":
            self.label2.setVisible(False)
            self.val_cb2.setVisible(False)
            self.val_cb1.setVisible(True)
            self.edit_val2.setVisible(False)
            self.edit_val4.setVisible(False)
            self.label4.setVisible(False)
            self.rate.setVisible(False)
            self.label1.setText("Start Value")

            self.label3.setText("Duration")
        if self.type_combo.currentText() == "Ramp":
            self.label2.setVisible(True)
            self.val_cb2.setVisible(True)
            self.val_cb1.setVisible(True)
            self.edit_val2.setVisible(True)
            self.edit_val4.setVisible(False)
            self.label4.setVisible(False)
            self.rate.setVisible(True)
            self.label3.setText("Speed")
            self.label1.setText("Start Value")
            self.label2.setText("Final Value")
        if self.type_combo.currentText() == "Sine Segment":
            self.label2.setVisible(True)
            self.val_cb2.setVisible(True)
            self.edit_val2.setVisible(True)
            self.edit_val4.setVisible(True)
            self.label4.setVisible(True)
            self.rate.setVisible(False)
            self.label3.setText("Duration")
            self.label1.setText("Amplitude")
            self.label2.setText("Frequency")
            self.val_cb1.setVisible(False)
            self.val_cb2.setVisible(False)
            # self.val_cb3.clear()
            # self.val_cb3.addItems(["min", "s", "ms"])

    def accept1(self):
        if self.type_combo.currentText() == "Isotherm":
            if not self.edit_val1.text() or not self.edit_val3.text():
                error_dialog = QMessageBox(QMessageBox.Critical, "Error", "Please enter the values", QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()

        if self.type_combo.currentText() == "Ramp":
            if not self.edit_val1.text() or not self.edit_val2.text() or not self.edit_val3.text():
                error_dialog = QMessageBox(QMessageBox.Critical, "Error", "Please enter the values", QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()
        if self.type_combo.currentText() == "Sine Segment":
            if not self.edit_val1.text() or not self.edit_val2.text() or not self.edit_val3.text() or not self.edit_val4.text():
                error_dialog = QMessageBox(QMessageBox.Critical, "Error", "Please enter the values", QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()


class SegmentType(Enum):
    NONE = 0,
    ISO = 1,
    RAMP = 2,
    SINE = 3


class SegmentData:
    def __init__(self,
                 segment_type: SegmentType,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 end_value: float):
        self.segment_type = segment_type
        self.start_time = start_time  # in seconds
        self.end_time = end_time  # in seconds
        self.start_value = start_value  # Volts or °C
        self.end_value = end_value  # Volts or °C

    def duration(self) -> float:
        return self.end_time - self.start_time


class IsoSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float):
        super().__init__(SegmentType.ISO, start_time, end_time, start_value, start_value)

    def __repr__(self):
        return f"IsoSegment({self.start_time}, {self.end_time}, {self.start_value})"


class RampSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 end_value: float):
        super().__init__(SegmentType.RAMP, start_time, end_time, start_value, end_value)

    def __repr__(self):
        return f"RampSegment({self.start_time}, {self.end_time}, {self.start_value}, {self.end_value})"

        # Volts or °C per second

    def rate(self) -> float:
        return (self.end_value - self.start_value) / self.duration()


class SineSegment(SegmentData):
    def __init__(self,
                 start_time: float,
                 end_time: float,
                 start_value: float,
                 amplitude: float,
                 frequency: float,
                 offset: float):
        super().__init__(SegmentType.SINE, start_time, end_time, start_value, start_value)

        self.amplitude = amplitude
        self.frequency = frequency
        self.offset = offset

    def __repr__(self):
        return f"SineSegment({self.start_time}, {self.end_time}, {self.start_value}, {self.end_value}, {self.amplitude}, {self.frequency}, {self.offset}  )"


class DataType(Enum):
    TIME = 1,
    TEMP = 2,
    VOLT = 3


class ProfileData:
    data_type: DataType
    segments: List[SegmentData]

    def __init__(self,
                 data_type: DataType,  # Y-axis
                 segments: List[SegmentData] = None):
        self.data_type = data_type
        if segments is None:
            segments = list()
        self.segments = segments

    def __str__(self):
        result = f"ProfileData(data_type={self.data_type}, segments=["
        for segment in self.segments:
            result += f"\n\t{segment}"
        result += "\n])"
        return result

    def __repr__(self):
        return f"ProfileData({self.data_type}, {self.segments})"


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    app.setStyle('Fusion')
    example = SetProg()
    example.show()
    sys.exit(app.exec())

