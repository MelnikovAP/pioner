import scipy
from PyQt5.QtCore import QRegExp
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import *

class SegmentDialog(QDialog):
    def __init__(self, type: str, mode: bool, pr_val: float = None, parent=None):
        QDialog.__init__(self, parent)
        reg_ex = QRegExp("[0-9.]*")

        # Создаем валидатор, используя регулярное выражение
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
        if pr_val is None:
            self.edit_val1.setText('')
        else:
            self.edit_val1.setText(str(pr_val))
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
        if not mode:
            self.type_combo.addItems(["Isotherm", "Ramp", "Sine Segment"])
        else:
            self.type_combo.addItems(["Isotherm", "Ramp"])
        self.trigger_label = QLabel("trigger on")
        self.checkbox_ttl = QCheckBox()
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
        hlayer4 = QHBoxLayout()

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

    def text_swap(self, a: QComboBox, text: str):
        pass

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
            if not self.edit_val1.text() or not self.edit_val2.text() or not self.edit_val3.text():
                error_dialog = QMessageBox(QMessageBox.Critical, "Error", "Please enter the values", QMessageBox.Ok,
                                           self)
                error_dialog.exec_()
            else:
                self.accept()