
import scipy
from PyQt5.QtCore import QRegExp
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import QPushButton, QShortcut
from PyQt5.QtGui import QKeySequence

from segmentdialog import SegmentDialog

class SetProgWidgetUI(QWidget):

    def __init__(self, parent=None):
        super(SetProgWidgetUI, self).__init__(parent)
        self.setFixedWidth(300)
        label_mode = QLabel('Mode:')
        hbox_head = QHBoxLayout()
        self.combo_box = QComboBox()
        self.combo_box.addItems(["fast", "modulation", "advanced"])

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setRowCount(0)
        self.table.setColumnWidth(0, 10)
        self.table.setColumnWidth(1, 83)
        self.table.setColumnWidth(2, 83)
        self.table.setColumnWidth(3, 10)

        self.table.horizontalHeader().setVisible(False)
        #self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        tot_dur_label = QLabel("t.dur=")
        self.tot_dur_val = QLabel('0')
        self.combo_box_val = QComboBox()
        self.combo_box_val.addItems(["°C", "V"])
        hbox_head.addWidget(tot_dur_label)
        hbox_head.addWidget(self.tot_dur_val)
        hbox_head.addWidget(self.combo_box_val)
        hbox_head.addWidget(label_mode)
        hbox_head.addWidget(self.combo_box)
        # add buttons
        self.button1 = QPushButton('+')
        self.button2 = QPushButton('-')
        self.button3 = QPushButton('Arm')
        self.button4 = QPushButton('Stop')
        self.button5 = QPushButton('Start')

        # horisontal separator
        hline = QWidget()
        hline.setFixedHeight(2)
        hline.setStyleSheet("background-color: #c4c4c4;")

        # add layouts
        hbox = QHBoxLayout()
        hbox.addWidget(self.button1)
        hbox.addWidget(self.button2)
        hbox.addWidget(self.button3)
        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.button4)
        hbox1.addWidget(self.button5)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox_head)
        vbox.addWidget(self.table)
        vbox.addWidget(hline)
        vbox.addLayout(hbox)
        vbox.addLayout(hbox1)
        self.shortcut_copy = QShortcut(QKeySequence("Ctrl+C"), self)
        self.shortcut_paste = QShortcut(QKeySequence("Ctrl+V"), self)
        self.shortcut_new_segment = QShortcut(QKeySequence("Ctrl+N"), self)
        self.setLayout(vbox)
        #self.button1.clicked.connect(lambda: self.add_layer(self.combo_box_val.currentText(), self.table.rowCount()))




# if __name__ == "__main__":
#   import sys

#  app = QApplication(sys.argv)

#  example = SetProgWidgetUI()
#  example.show()
#  sys.exit(app.exec())

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
