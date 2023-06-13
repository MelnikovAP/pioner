import sys
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import numpy as np
import json
from enum import Enum
from typing import List
from segmentdialog import SegmentDialog
from dataclass import *


class SetProg(QWidget):
    def __init__(self, parent=None):
        super(SetProg, self).__init__(parent)
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

        for i in range(self.mainTabWidget.count()):
            tab = self.mainTabWidget.widget(i)
            profiles_data[i] = tab.get_dict()
        print(profiles_data)
        return profiles_data


class ProfileWidget(QWidget):
    def __init__(self, name: str, parent=None):
        super(ProfileWidget, self).__init__(parent=parent)
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
            buttrow.clicked.connect(lambda checked, x=row_number: self.add_layer(x))
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

            self.typecbox.setEnabled(False)

    def add_layer(self, x: int):
        dialog = SegmentDialog(self.typecbox.currentText(),False)
        if dialog.exec_() == QDialog.Accepted:

            if x != self.tableWidget.rowCount():
                row_number = x
                self.tableWidget.insertRow(row_number)
                self.tableWidget.removeRow(row_number + 1)
            # Create and set the button widget
            else:

                row_number = self.tableWidget.rowCount()
                self.tableWidget.insertRow(row_number)
            mode_type = dialog.type_combo.currentText()
            # Create and set the button widget
            buttrow = QPushButton(mode_type)
            buttrow.setObjectName("but" + str(row_number))
            buttrow.clicked.connect(lambda checked, x=row_number: self.add_layer(x))
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

            self.typecbox.setEnabled(False)

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






'''if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)

    app.setStyle('Fusion')
    example = SetProg()
    example.show()
    sys.exit(app.exec())'''