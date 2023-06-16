from silx.gui import qt

class progSegmentDialogUi(qt.QDialog):
    def __init__(self, parent=None):
        super(progSegmentDialogUi, self).__init__(parent)
    
        reg_ex = qt.QRegExp("[0-9.]*")
        # Создаем валидатор, используя регулярное выражение
        validator = qt.QRegExpValidator(reg_ex)

        self.setWindowTitle("Add Option")
        self.val_cb1 = qt.QLabel()
        self.val_cb2 = qt.QLabel()
        self.rate = qt.QLabel()
        self.val_cb3 = qt.QComboBox()
        self.val_cb3.addItems(['s', 'ms', 'min'])
        self.val_cb3.setMinimumSize(80, 25)
        self.horlayout0 = qt.QHBoxLayout()
        self.horlayout1 = qt.QHBoxLayout()
        self.edit_val1 = qt.QLineEdit()
        self.edit_val1.setValidator(validator)

        self.edit_val2 = qt.QLineEdit()
        self.edit_val2.setValidator(validator)
        self.edit_val4 = qt.QLineEdit()  # offset
        self.edit_val4.setValidator(validator)

        self.edit_val3 = qt.QLineEdit()
        self.edit_val3.setValidator(validator)
        self.label1 = qt.QLabel("val1")
        self.label2 = qt.QLabel("val2")
        self.label4 = qt.QLabel("Offset")
        self.label3 = qt.QLabel("Duration")
        self.type_label = qt.QLabel("Choose type")
        self.type_combo = qt.QComboBox()

        self.trigger_label = qt.QLabel("trigger on")
        self.checkbox_ttl = qt.QCheckBox()
        self.button_box = qt.QDialogButtonBox(qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel)
        layer1 = qt.QVBoxLayout()
        vlayer1 = qt.QVBoxLayout()
        vlayer2 = qt.QVBoxLayout()
        vlayer3 = qt.QVBoxLayout()
        vlayer4 = qt.QVBoxLayout()
        vlayer5 = qt.QVBoxLayout()
        hlayer1 = qt.QHBoxLayout()
        hlayer2 = qt.QHBoxLayout()
        hlayer3 = qt.QHBoxLayout()
        hlayer4 = qt.QHBoxLayout()

        self.layout = qt.QVBoxLayout()

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
        hlayer4.addWidget(self.checkbox_ttl)
        hlayer4.addWidget(self.trigger_label)
        hlayer4.addWidget(self.button_box)
        self.horlayout0.addLayout(vlayer1)
        self.horlayout0.addLayout(vlayer2)
        self.horlayout0.addLayout(vlayer3)
        self.horlayout0.addLayout(vlayer4)
        self.horlayout0.addLayout(vlayer5)

        self.layout.addLayout(self.horlayout0)

        layer1.addLayout(self.layout)
        layer1.addLayout(hlayer4)
        self.setLayout(layer1)
        self.change_type()
        self.type_combo.currentTextChanged.connect(self.change_type)

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

class progSegmentDialog(progSegmentDialogUi):
    def __init__(self, type: str, simple_mode: bool, pr_val: float = None, parent=None):
        super(progSegmentDialog, self).__init__(parent)

        self.val_cb1.setText(type)
        self.val_cb2.setText(type)
        self.rate.setText(type + "/")

        self.edit_val1.setText(str(pr_val) if pr_val else '')
        self.type_combo.addItems(["Isotherm", "Ramp"] if simple_mode \
                                    else ["Isotherm", "Ramp", "Sine Segment"])

        self.button_box.accepted.connect(self.custom_accept)
        self.button_box.rejected.connect(self.reject)

    def custom_accept(self):
        if self.type_combo.currentText() == "Isotherm":
            if not self.edit_val1.text() or not self.edit_val3.text():
                error_dialog = qt.QMessageBox(qt.QMessageBox.Critical, "Error", "Please enter the values", qt.QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()

        if self.type_combo.currentText() == "Ramp":
            if not self.edit_val1.text() or not self.edit_val2.text() or not self.edit_val3.text():
                error_dialog = qt.QMessageBox(qt.QMessageBox.Critical, "Error", "Please enter the values", qt.QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()
        if self.type_combo.currentText() == "Sine Segment":
            if not self.edit_val1.text() or not self.edit_val2.text() or not self.edit_val3.text():
                error_dialog = qt.QMessageBox(qt.QMessageBox.Critical, "Error", "Please enter the values", qt.QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()


if __name__ == "__main__":
    import sys
    app = qt.QApplication(sys.argv)

    app.setStyle('Fusion')
    example = progSegmentDialog("Isotherm", False)
    example.show()
    sys.exit(app.exec())