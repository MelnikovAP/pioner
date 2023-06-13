
import scipy
from PyQt5.QtCore import *
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import *
from segmentdialog import SegmentDialog
from SetProgUI import SetProgWidgetUI
from dataclass import *
from AdvancedSetProg import SetProg
from PyQt5.QtWidgets import QMessageBox


class SetProgWidget(SetProgWidgetUI):

    def __init__(self, parent=None):
        super(SetProgWidget, self).__init__(parent)
        # add functions on buttons
        self.button1.clicked.connect(lambda: self.add_layer(self.combo_box_val.currentText(), self.table.rowCount()))
        self.combo_box.currentTextChanged.connect(lambda: self.open_advanced_interface())
        # self.button1.clicked.connect(self.add_action)
        self.button2.clicked.connect(lambda: self.mass_del())
        self.button3.clicked.connect(lambda: self.get_dict())
        self.button4.clicked.connect(self.add_action)
        self.button5.clicked.connect(self.add_action)
        self.shortcut_copy.activated.connect(self.copy_selected_rows)
        self.shortcut_paste.activated.connect(self.paste_copied_rows)
        self.shortcut_new_segment.activated.connect(lambda: self.add_layer(self.combo_box_val.currentText(), self.table.rowCount()))

    @staticmethod
    def add_action():
        print("hello")

    def add_layer(self, type_v: str, x: int):
        if self.table.rowCount() != 0:
            meme = self.sum_numbers_and_extract_text()
            dialog = SegmentDialog(type_v, True, meme)
        else:
            dialog = SegmentDialog(type_v, True)
        if dialog.exec_() == QDialog.Accepted:
            if x != self.table.rowCount():
                row_number = x
                self.table.insertRow(row_number)
                self.table.removeRow(row_number + 1)
            else:
                self.table.insertRow(x)
                row_number = x
            # Create and set the button widget
            type_val = dialog.type_combo.currentText()
            mode = type_val
            f_val = dialog.edit_val1.text()
            dur_val = dialog.edit_val3.text()
            dur_type = dialog.val_cb3.currentText()
            trigger = dialog.checkbox_ttl.isChecked()
            dur_item = QTableWidgetItem(dur_val + " " + dur_type)

            mode_item = QTableWidgetItem()

            val_item = QTableWidgetItem()

            ttl_mark = QTableWidgetItem()

            if mode == "Isotherm":
                mode_item = QTableWidgetItem('→')
                val_item = QTableWidgetItem(f_val + " " + type_v)

            elif mode == "Ramp":
                to_val = dialog.edit_val2.text()
                val_item = QTableWidgetItem(f_val + "..." + to_val + ' ' + type_v)
                dur_item = QTableWidgetItem(dur_val + ' ' + type_v + '/' + dur_type)

                if f_val > to_val:
                    mode_item = QTableWidgetItem('↘')
                else:
                    mode_item = QTableWidgetItem('↗')

            if trigger:
                ttl_mark = QTableWidgetItem("ttl")

            dur_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            mode_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ttl_mark.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_number, 0, mode_item)
            self.table.setItem(row_number, 1, val_item)
            self.table.setItem(row_number, 2, dur_item)
            self.table.setItem(row_number, 3, ttl_mark)
            # self.tot_dur_val.setText(str(float(self.tot_dur_val.text()) + duration))
            self.combo_box_val.setEnabled(False)
            self.sum_numbers_and_extract_text()

    def copy_selected_rows(self):
        # get a rows
        selected_ranges = self.table.selectedRanges()
        selected_rows = set()

        #get all selected rows
        for selected_range in selected_ranges:
            start_row = selected_range.topRow()
            end_row = selected_range.bottomRow()
            for row in range(start_row, end_row + 1):
                selected_rows.add(row)

        # create a string
        self.copied_rows = []
        for row in selected_rows:
            row_text = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item is not None:
                    row_text.append(item.text())
                else:
                    row_text.append("")
            self.copied_rows.append(row_text)

    def sum_numbers_and_extract_text(self):
        total_sum: float = 0
        extracted_text = ""
        lastval=0
        for row in range(self.table.rowCount()):
            # get a cell items
            item_type = self.table.item(row, 0).text()
            table_item = self.table.item(row, 2)
            table_vals = self.table.item(row, 1)

            if table_item is not None:
                # separate to parts
                parts = table_item.text().split()
                partsval = table_vals.text().split()
                lastval=partsval[0]
                if item_type == '→':
                    extracted_text = " ".join(parts[1:])
                    if extracted_text == "s":
                        total_sum += float(parts[0]) / 60
                    elif extracted_text == "ms":
                        total_sum += float(parts[0]) / 60000
                    elif extracted_text == "min":
                        total_sum += float(parts[0])

                elif item_type == '↘' or item_type == '↗':
                    extracted_text = "/".join(parts[1:])
                    print(extracted_text)
                    if table_vals is not None:
                        partsval = table_vals.text().split()
                        vals = []
                        values = partsval[0].split('...')
                        for value in values:
                            try:
                                val = float(value)
                                vals.append(val)
                                print(vals)
                            except ValueError:
                                pass
                        if len(vals) == 2:
                            time = abs(vals[0] - vals[1]) / float(parts[0])
                            print(str(time))
                            lastval=vals[1]

                            if extracted_text == "°C/s" or extracted_text == "V/s":
                                total_sum += time / 60
                            elif extracted_text == "°C/ms" or extracted_text == "V/ms":
                                total_sum += time / 60000
                            elif extracted_text == "°C/min" or extracted_text == "V/min":
                                total_sum += time

        self.tot_dur_val.setText(str(round(total_sum)) + ' min')
        return lastval

    def paste_copied_rows(self):
        if not self.copied_rows:
            return

        # insert rows
        last_row = self.table.rowCount()
        for row_text in self.copied_rows:
            self.table.insertRow(last_row)
            for col, item_text in enumerate(row_text):
                item = QTableWidgetItem(item_text)
                if col in (0, 1):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                self.table.setItem(last_row, col, item)
            last_row += 1
            self.sum_numbers_and_extract_text()

    def copy_and_paste(self):
        # get a selected part of table
        selected = self.table.selectedRanges()[0]
        start_row = selected.topRow()
        end_row = selected.bottomRow()
        start_col = selected.leftColumn()
        end_col = selected.rightColumn()

        # fragment to string
        text = ""
        for row in range(start_row, end_row + 1):
            row_text = ""
            for col in range(start_col, end_col + 1):
                item = self.table.item(row, col)
                if item is not None:
                    row_text += item.text() + "\t"
            text += row_text.strip() + "\n"

        # insert string in end of table
        last_row = self.table.rowCount()
        self.table.insertRow(last_row)
        for i, value in enumerate(text.strip().split("\n")):
            row_number = last_row + i
            items = value.split("\t")
            if len(items) < 4:
                mode_item = QTableWidgetItem(items[0])
                mode_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                val_item = QTableWidgetItem(items[1])
                val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                dur_item = QTableWidgetItem(items[2])
                dur_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                ttl_mark = QTableWidgetItem('')
                ttl_mark.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            else:
                mode_item = QTableWidgetItem(items[0])
                mode_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                val_item = QTableWidgetItem(items[1])
                val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                dur_item = QTableWidgetItem(items[2])
                dur_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                ttl_mark = QTableWidgetItem(items[3])
                ttl_mark.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row_number, 0, mode_item)
            self.table.setItem(row_number, 1, val_item)
            self.table.setItem(row_number, 2, dur_item)
            self.table.setItem(row_number, 3, ttl_mark)

    def mass_del(self):
        # Function to delete selected rows from the table widget
        row_number = self.table.rowCount()
        # If there is a selection in the table widget, delete the selected rows
        if self.table.selectionModel().hasSelection():
            # Create an empty list to store the selected indices
            index_list = []

            # Loop through the selected rows and add their indices to the index list
            for model_index in self.table.selectionModel().selectedRows():
                index = QPersistentModelIndex(model_index)
                index_list.append(index)

            # Loop through the index list and remove the corresponding rows from the table widget
            for index in index_list:
                self.table.removeRow(index.row())
        # If there is no selection, remove the last row in the table widget
        else:
            self.table.removeRow(row_number - 1)

        # Loop through the rows of the table widget and update the object names of the buttons
        for i in range(row_number):
            if self.table.cellWidget(i, 0) is not None:
                self.table.cellWidget(i, 0).setObjectName("but" + str(i))

        # If the table widget is now empty, enable the typecbox combo box
        if self.table.rowCount() == 0:
            self.combo_box_val.setEnabled(True)

    def get_dict(self):
        # Get the currently selected type from a combo box
        typeval = self.combo_box_val.currentText()

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

        total_sum: float = 0
        extracted_text = ""
        lastval = 0
        for row in range(self.table.rowCount()):

            item_type = self.table.item(row, 0).text()
            table_item = self.table.item(row, 2)
            table_vals = self.table.item(row, 1)
            vals = []
            stmoment = total_sum
            if table_item is not None:

                parts = table_item.text().split()
                partsval = table_vals.text().split()
                lastval = partsval[0]
                if item_type == '→':
                    vals = partsval[0].split(' ')
                    extracted_text = " ".join(parts[1:])
                    if extracted_text == "s":
                        total_sum += float(parts[0])
                    elif extracted_text == "ms":
                        total_sum += float(parts[0]) / 1000
                    elif extracted_text == "min":
                        total_sum += float(parts[0]) * 60
                    endmoment = total_sum
                    stval = vals[0]
                    segment = IsoSegment(stmoment, endmoment, stval)
                    segments.append(segment)

                elif item_type == '↘' or item_type == '↗':
                    extracted_text = "/".join(parts[1:])
                    print(extracted_text)
                    if table_vals is not None:
                        partsval = table_vals.text().split()

                        values = partsval[0].split('...')
                        for value in values:
                            try:
                                val = float(value)
                                vals.append(val)
                                print(vals)
                            except ValueError:
                                pass
                        if len(vals) == 2:
                            time = abs(vals[0] - vals[1]) / float(parts[0])
                            print(str(time))
                            lastval = vals[1]

                            if extracted_text == "°C/s" or extracted_text == "V/s":
                                total_sum += time
                            elif extracted_text == "°C/ms" or extracted_text == "V/ms":
                                total_sum += time / 1000
                            elif extracted_text == "°C/min" or extracted_text == "V/min":
                                total_sum += time*60
                        stval = vals[0]
                        endval = vals[1]
                        endmoment = total_sum
                        segment = RampSegment(stmoment, endmoment, stval, endval)
                        segments.append(segment)


       # Determine the data type based on the selected type in the combo box
        if typeval == "V":
            data_type = DataType.VOLT
        else:
            data_type = DataType.TEMP

        # Create a ProfileData object using the collected data
        data = ProfileData(data_type, segments)

        # Return the created ProfileData object
        print (data)

    def open_advanced_interface(self):
        if self.combo_box.currentText() == "advanced":
            dialog = QMessageBox()
            dialog.setWindowTitle("Confirmation")
            dialog.setText("Open advanced mode?")
            dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            dialog.setDefaultButton(QMessageBox.Ok)
            result = dialog.exec_()

            if result == QMessageBox.Ok:
                self.set_prog = SetProg()
                #self.hide()
                self.set_prog.show()
