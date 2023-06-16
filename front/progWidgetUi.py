from silx.gui import qt

class progWidgetUi(qt.QWidget):

    def __init__(self, parent=None):
        super(progWidgetUi, self).__init__(parent)
        self.setFixedWidth(300)
        label_mode = qt.QLabel('Mode:')
        hbox_head = qt.QHBoxLayout()
        self.combo_box = qt.QComboBox()
        self.combo_box.addItems(["fast", "modulation", "advanced"])

        self.table = qt.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.table.setRowCount(0)
        self.table.setColumnWidth(0, 10)
        self.table.setColumnWidth(1, 83)
        self.table.setColumnWidth(2, 83)
        self.table.setColumnWidth(3, 10)

        self.table.horizontalHeader().setVisible(False)
        #self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)

        tot_dur_label = qt.QLabel("t.dur=")
        self.tot_dur_val = qt.QLabel('0')
        self.combo_box_val = qt.QComboBox()
        self.combo_box_val.addItems(["°C", "V"])
        hbox_head.addWidget(tot_dur_label)
        hbox_head.addWidget(self.tot_dur_val)
        hbox_head.addWidget(self.combo_box_val)
        hbox_head.addWidget(label_mode)
        hbox_head.addWidget(self.combo_box)
        # add buttons
        self.button1 = qt.QPushButton('+')
        self.button2 = qt.QPushButton('-')
        self.button3 = qt.QPushButton('Arm')
        self.button4 = qt.QPushButton('Stop')
        self.button5 = qt.QPushButton('Start')

        # horisontal separator
        hline = qt.QWidget()
        hline.setFixedHeight(2)
        hline.setStyleSheet("background-color: #c4c4c4;")

        # add layouts
        hbox = qt.QHBoxLayout()
        hbox.addWidget(self.button1)
        hbox.addWidget(self.button2)
        hbox.addWidget(self.button3)
        hbox1 = qt.QHBoxLayout()
        hbox1.addWidget(self.button4)
        hbox1.addWidget(self.button5)

        vbox = qt.QVBoxLayout()
        vbox.addLayout(hbox_head)
        vbox.addWidget(self.table)
        vbox.addWidget(hline)
        vbox.addLayout(hbox)
        vbox.addLayout(hbox1)
        self.shortcut_copy = qt.QShortcut(qt.QKeySequence("Ctrl+C"), self)
        self.shortcut_paste = qt.QShortcut(qt.QKeySequence("Ctrl+V"), self)
        self.shortcut_new_segment = qt.QShortcut(qt.QKeySequence("Ctrl+N"), self)
        self.setLayout(vbox)
        #self.button1.clicked.connect(lambda: self.add_layer(self.combo_box_val.currentText(), self.table.rowCount()))

if __name__ == "__main__":
    import sys
    app = qt.QApplication(sys.argv)
    example = progWidgetUi()
    example.show()
    sys.exit(app.exec())
