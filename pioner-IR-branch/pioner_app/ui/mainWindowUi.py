from silx.gui import icons, qt

from pioner_app.ui.widgets.input_gains_panel import InputGainsPanel

from pioner_app.ui.widgets.procFastHeatWidget import procFastHeatWidget
from pioner_app.ui.widgets.resultsDataWidget import resultsDataWidget
from pioner_app.ui.widgets.signalswidget import SignalsWidget
from pioner_app.ui.widgets.SetProg_widget import SetProg
from pioner_app.ui.widgets.exp_widget import ProfileWidget
from pioner_app.ui.widgets.modulationWidget import SlowHeatingWidget
from pioner_app.ui.widgets.simpleProcessWidget import SimpleProcessWidget
from pioner_app.ui.widgets.universalResultsWidget import UniversalResultsWidget
from pioner_app.ui.h_windows import calibWindow
from PyQt5.QtCore import Qt, QTimer
import numpy as np

from pioner_app.hardware.daq_controller import get_daq_controller


class mainWindowUi(qt.QWidget):
    def __init__(self, parent=None):
        super(mainWindowUi, self).__init__(parent)

        self.setWindowTitle("PIONER Lab")
        self.setMinimumHeight(800)

        mainLayout = qt.QHBoxLayout()
        self.setLayout(mainLayout)

        short_label_width = 55
        short_button_width = 60
        long_label_width = 60
        button_height = 20
        short_line_input_width = 60
        font = qt.QFont()

        leftLayout = qt.QVBoxLayout()
        mainLayout.addLayout(leftLayout)

        systemBox = qt.QGroupBox("System")
        leftLayout.addWidget(systemBox, 0)
        lout_0 = qt.QVBoxLayout()
        systemBox.setLayout(lout_0)

        lout_1 = qt.QHBoxLayout()
        lout_0.addLayout(lout_1)
        self.sysOnButton = qt.QPushButton(" ON ")
        font.setBold(True)
        self.sysOnButton.setFont(font)
        self.sysOnButton.setMinimumHeight(23)
        lout_1.addWidget(self.sysOnButton, 1)
        self.sysOffButton = qt.QPushButton("OFF")
        font.setBold(True)
        self.sysOffButton.setFont(font)
        self.sysOffButton.setMinimumHeight(23)
        lout_1.addWidget(self.sysOffButton, 1)
        self.sysSetupButton = qt.QToolButton()
        self.sysSetupButton.setToolTip("Device settings")
        self.sysSetupButton.setIcon(icons.getQIcon('item-object'))
        lout_1.addWidget(self.sysSetupButton, 0)
        lout_1.setSpacing(1)
        self.tangocheck = qt.QRadioButton("Use Tango")
        self.dirconn = qt.QRadioButton("Use direct connection")
        self.sysNoHardware = qt.QCheckBox(" run without hardware/ use wo raspi")
        lout_0.addWidget(self.tangocheck)
        lout_0.addWidget(self.dirconn)
        lout_0.addWidget(self.sysNoHardware)

        self.experimentBox = qt.QGroupBox("Experiment")
        leftLayout.addWidget(self.experimentBox, 0)
        lout_0 = qt.QVBoxLayout()
        self.experimentBox.setLayout(lout_0)

        lout_0.addStretch()
        hline = qt.QFrame()
        hline.setFrameShape(qt.QFrame.HLine)
        hline.setStyleSheet("color: rgb(220, 220, 220);")
        lout_0.addWidget(hline)
        lout_0.addStretch()

        lout_1 = qt.QVBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.setSpacing(1)
        lout_1.addWidget(qt.QLabel("Data path"))
        lout_2 = qt.QHBoxLayout()
        lout_2.setSpacing(0)
        lout_1.addLayout(lout_2)
        self.sysDataPathInput = qt.QLineEdit()
        self.sysDataPathInput.setMinimumWidth(150)
        lout_2.addWidget(self.sysDataPathInput)
        self.sysDataPathButton = qt.QToolButton()
        self.sysDataPathButton.setToolTip("Browse data path")
        self.sysDataPathButton.setIcon(icons.getQIcon('document-open'))
        lout_2.addWidget(self.sysDataPathButton)

        lout_1 = qt.QVBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.setSpacing(3)
        lout_1.addWidget(qt.QLabel("Calibration path"))
        lout_2 = qt.QHBoxLayout()
        lout_1.addLayout(lout_2)
        lout_2.setSpacing(0)
        self.calibPathInput = qt.QLineEdit()
        lout_2.addWidget(self.calibPathInput)
        self.calibPathButton = qt.QToolButton()
        self.calibPathButton.setToolTip("Browse calibration path")
        self.calibPathButton.setIcon(icons.getQIcon('document-open'))
        lout_2.addWidget(self.calibPathButton)
        lout_3 = qt.QHBoxLayout()
        lout_3.setSpacing(1)
        lout_1.addLayout(lout_3)
        lout_3.addStretch()
        self.calibViewButton = qt.QPushButton("View")
        self.calibViewButton.setFixedWidth(short_button_width)
        lout_3.addWidget(self.calibViewButton)
        self.calibApplyButton = qt.QPushButton("Apply")
        self.calibApplyButton.setFixedWidth(short_button_width)
        lout_3.addWidget(self.calibApplyButton)

        lout_0.addStretch()
        hline = qt.QFrame()
        hline.setFrameShape(qt.QFrame.HLine)
        hline.setStyleSheet("color: rgb(220, 220, 220);")
        lout_0.addWidget(hline)
        lout_0.addStretch()

        lout_1 = qt.QVBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.setSpacing(3)
        lout_1.addWidget(qt.QLabel("Scan"))
        lout_2 = qt.QHBoxLayout()
        lout_1.addLayout(lout_2)
        lout_2.setSpacing(3)
        lout_2.addStretch()
        lout_2.addWidget(qt.QLabel("Sample rate:"))
        self.scanSampleRateInput = qt.QLineEdit()
        self.scanSampleRateInput.setMaximumWidth(short_line_input_width)
        lout_2.addWidget(self.scanSampleRateInput)
        unit = qt.QLabel("Hz")
        unit.setFixedWidth(20)
        lout_2.addWidget(unit)
        lout_3 = qt.QHBoxLayout()
        lout_1.addLayout(lout_3)
        lout_3.setSpacing(1)
        lout_3.addStretch()
        self.resetScanSampleRateButton = qt.QPushButton("Reset")
        self.resetScanSampleRateButton.setFixedWidth(short_button_width)
        lout_3.addWidget(self.resetScanSampleRateButton)
        self.applyScanSampleRateButton = qt.QPushButton("Apply")
        self.applyScanSampleRateButton.setFixedWidth(short_button_width)
        lout_3.addWidget(self.applyScanSampleRateButton)

        lout_0.addStretch()
        hline = qt.QFrame()
        hline.setFrameShape(qt.QFrame.HLine)
        hline.setStyleSheet("color: rgb(220, 220, 220);")
        lout_0.addWidget(hline)
        lout_0.addStretch()

        lout_1 = qt.QVBoxLayout()
        lout_0.addLayout(lout_1)
        lout_1.setSpacing(3)
        lout_1.addWidget(qt.QLabel("Modulation"))
        lout_2 = qt.QHBoxLayout()
        lout_1.addLayout(lout_2)
        lout_2.setSpacing(3)
        lout_2.addStretch()
        lout_2.addWidget(qt.QLabel("Frequency:"))
        self.freqInput = qt.QLineEdit()
        self.freqInput.setMaximumWidth(short_line_input_width)
        lout_2.addWidget(self.freqInput)
        units = qt.QLabel("Hz")
        units.setFixedWidth(20)
        lout_2.addWidget(units)
        lout_3 = qt.QHBoxLayout()
        lout_1.addLayout(lout_3)
        lout_3.setSpacing(3)
        lout_3.addStretch()
        lout_3.addWidget(qt.QLabel("Amplitude:"))
        self.amplitudeInput = qt.QLineEdit()
        self.amplitudeInput.setMaximumWidth(short_line_input_width)
        lout_3.addWidget(self.amplitudeInput)
        units = qt.QLabel("mA")
        units.setFixedWidth(20)
        lout_3.addWidget(units)
        lout_4 = qt.QHBoxLayout()
        lout_1.addLayout(lout_4)
        lout_4.setSpacing(3)
        lout_4.addStretch()
        lout_4.addWidget(qt.QLabel("Offset:"))
        self.offsetInput = qt.QLineEdit()
        self.offsetInput.setMaximumWidth(short_line_input_width)
        lout_4.addWidget(self.offsetInput)
        units = qt.QLabel("mA")
        units.setFixedWidth(20)
        lout_4.addWidget(units)
        lout_5 = qt.QHBoxLayout()
        lout_1.addLayout(lout_5)
        lout_5.setSpacing(1)
        lout_5.addStretch()
        self.resetModulationParamsButton = qt.QPushButton("Reset")
        self.resetModulationParamsButton.setFixedWidth(short_button_width)
        lout_5.addWidget(self.resetModulationParamsButton)
        self.applyModulationParamsButton = qt.QPushButton("Apply")
        self.applyModulationParamsButton.setFixedWidth(short_button_width)
        lout_5.addWidget(self.applyModulationParamsButton)

        self.inputGainsToggleButton = qt.QToolButton()
        self.inputGainsToggleButton.setText("Input gains")
        self.inputGainsToggleButton.setCheckable(True)
        self.inputGainsToggleButton.setChecked(False)
        self.inputGainsToggleButton.setToolButtonStyle(qt.Qt.ToolButtonTextBesideIcon)
        self.inputGainsToggleButton.setArrowType(qt.Qt.RightArrow)
        lout_1.addWidget(self.inputGainsToggleButton)

        self.inputGainsPanel = InputGainsPanel(self)
        self.inputGainsPanel.setVisible(False)
        lout_1.addWidget(self.inputGainsPanel)

        leftLayout.addStretch(2)

        lout_0 = qt.QVBoxLayout()
        leftLayout.addLayout(lout_0, 0)
        logo = qt.QLabel()
        logo.setAlignment(qt.Qt.AlignHCenter)
        pixmap = qt.QPixmap("./res/logo.png").scaledToWidth(70)
        logo.setPixmap(pixmap)
        lout_0.addWidget(logo)
        sign = qt.QLabel("Nanocontrol v.0.1")
        sign.setAlignment(qt.Qt.AlignHCenter)
        lout_0.addWidget(sign)

        rightLayout = qt.QVBoxLayout()
        mainLayout.addLayout(rightLayout, 1)

        self.mainTabWidget = qt.QTabWidget()
        self.signalsTab = qt.QWidget()
        self.mainTabWidget.addTab(self.signalsTab, "Signals")
        self.controlTab = qt.QWidget()
        self.mainTabWidget.addTab(self.controlTab, "Control")
        self.resultTab = qt.QWidget()
        self.mainTabWidget.addTab(self.resultTab, "Result")
        self.universalResultTab = qt.QWidget()
        self.mainTabWidget.addTab(self.universalResultTab, "Result Browser")
        self.slowheatingTab = qt.QWidget()
        self.mainTabWidget.addTab(self.slowheatingTab, "Slow Heating")
        self.addNewTab = qt.QWidget()
        self.mainTabWidget.addTab(self.addNewTab, "+")
        self.mainTabWidget.setTabsClosable(True)
        self.mainTabWidget.tabBar().setTabButton(0, qt.QTabBar.RightSide, None)
        self.mainTabWidget.tabBar().setTabButton(1, qt.QTabBar.RightSide, None)
        self.mainTabWidget.tabBar().setTabButton(2, qt.QTabBar.RightSide, None)
        self.mainTabWidget.tabBar().setTabButton(3, qt.QTabBar.RightSide, None)
        self.mainTabWidget.tabBar().setTabButton(4, qt.QTabBar.RightSide, None)
        rightLayout.addWidget(self.mainTabWidget)

        self.valueswind = ValuesWidget()
        rightLayout.addWidget(self.valueswind)

        lout_0 = qt.QHBoxLayout()
        self.signalsTab.setLayout(lout_0)
        self.signalsWidget = SignalsWidget(parent=self)
        lout_0.addWidget(self.signalsWidget)

        lout_0 = qt.QVBoxLayout()
        self.controlTab.setLayout(lout_0)
        self.exp_widget = ProfileWidget(parent=self)
        lout_0.addWidget(self.exp_widget)

        lout_0 = qt.QHBoxLayout()
        self.resultTab.setLayout(lout_0)
        self.resultsDataWidget = resultsDataWidget(parent=self)
        lout_0.addWidget(self.resultsDataWidget)

        lout_0 = qt.QHBoxLayout()
        self.universalResultTab.setLayout(lout_0)
        self.universalResultsWidget = UniversalResultsWidget(parent=self)
        lout_0.addWidget(self.universalResultsWidget)

        lout_0 = qt.QHBoxLayout()
        self.slowheatingTab.setLayout(lout_0)
        self.slowheatingWidget = SlowHeatingWidget(parent=self)
        lout_0.addWidget(self.slowheatingWidget)

        self.acquisitionTimer = qt.QTimer(self)

        lout_0 = qt.QHBoxLayout()
        rightLayout.addLayout(lout_0)
        lout_0.setSpacing(1)
        lout_0.addWidget(qt.QLabel("Hardware:"))

        self.hardware_label = qt.QLabel(' ---')
        self.hardware_label.setFixedWidth(120)
        lout_0.addWidget(self.hardware_label)

        lout_0.addWidget(qt.QLabel("Status:"))

        self.status_label = qt.QLabel(' ---')
        self.status_label.setFixedWidth(100)
        lout_0.addWidget(self.status_label)
        lout_0.addStretch()
        lout_0.addWidget(qt.QLabel("Progress:"))
        self.progressBar = qt.QProgressBar()
        lout_0.addWidget(self.progressBar, 1)

        self.mainTabWidget.currentChanged.connect(self.add_tab_to_mainTabWidget)
        self.mainTabWidget.tabCloseRequested.connect(self.close_tab_in_mainTabWidget)
        self.inputGainsToggleButton.toggled.connect(self.toggle_input_gains_box)

    def toggle_input_gains_box(self, checked):
        self.inputGainsPanel.setVisible(bool(checked))
        self.inputGainsToggleButton.setArrowType(qt.Qt.DownArrow if checked else qt.Qt.RightArrow)

    def setComboBox_changed(self):
        text = self.setComboBox.currentText()
        if text == "Temp":
            self.setInputUnits.setText("??C")
        if text == "Volt":
            self.setInputUnits.setText("V")

    def add_tab_to_mainTabWidget(self, i):
        if self.mainTabWidget.tabText(i) == "+":
            tab_types = ("Process fast heating",
                        "Simple data processing",
                        "Process slow heating",
                        "Process with custom workflow",
                        "Advanced process control")
            tab_type, ok = qt.QInputDialog.getItem(self, "Choose type:",
                "New tab", tab_types, 0, False)
            if ok and tab_type:
                self.newTab = qt.QWidget()
                self.newTab.layout = qt.QVBoxLayout()
                self.mainTabWidget.insertTab(i, self.newTab, tab_type)
                self.mainTabWidget.setCurrentIndex(i)

                if tab_type == "Process fast heating":
                    self.newTabWidget = procFastHeatWidget(self)
                    self.newTab.layout.addWidget(self.newTabWidget)

                if tab_type == "Simple data processing":
                    self.newTabWidget = SimpleProcessWidget(self)
                    self.newTab.layout.addWidget(self.newTabWidget)

                if tab_type == "Advanced process control":
                    self.newTabWidget = SetProg(self)
                    self.newTab.layout.addWidget(self.newTabWidget)
                self.newTab.setLayout(self.newTab.layout)

    def close_tab_in_mainTabWidget(self, i):
        self.mainTabWidget.setCurrentIndex(i-1)
        self.mainTabWidget.removeTab(i)

    def App_execute(self):
        return None


class ValuesWidget(qt.QGroupBox):

    def __init__(self, parent=None):
        super().__init__("Values", parent)

        self.ctrl = get_daq_controller()

        self.short_label_width = 80
        self.short_button_width = 60

        self._build_ui()

    def _add_value_row(self, layout, title, attr_name, width=None):
        row = qt.QHBoxLayout()
        layout.addLayout(row)
        label = qt.QLabel(title)
        label.setAlignment(qt.Qt.AlignRight)
        row.addWidget(label)
        value = qt.QLabel(" ---")
        value.setFixedWidth(width or self.short_label_width)
        value.setAlignment(qt.Qt.AlignLeft)
        row.addWidget(value)
        setattr(self, attr_name, value)

    def _build_ui(self):
        root = qt.QHBoxLayout(self)
        root.setSpacing(12)

        col1 = qt.QVBoxLayout()
        self._add_value_row(col1, "R htr abs:", "rhtrabsValueLabel")
        self._add_value_row(col1, "R htr dyn:", "rhtrdynValueLabel")
        self._add_value_row(col1, "U mod htr:", "umodhtrValueLabel")
        self._add_value_row(col1, "I htr:", "ihtrValueLabel")
        root.addLayout(col1)

        col2 = qt.QVBoxLayout()
        self._add_value_row(col2, "T aux:", "tauxValueLabel")
        self._add_value_row(col2, "T tpl:", "ttplValueLabel")
        self._add_value_row(col2, "T htr:", "thtrValueLabel")
        self._add_value_row(col2, "T htr dyn:", "thtrdynValueLabel")
        root.addLayout(col2)

        col3 = qt.QVBoxLayout()
        self._add_value_row(col3, "T-error:", "terrorValueLabel", width=40)
        self.terror0Button = qt.QPushButton("> 0 <")
        self.terror0Button.setFixedWidth(self.short_button_width)
        col3.addWidget(self.terror0Button)
        self.tresetButton = qt.QPushButton("reset")
        self.tresetButton.setFixedWidth(self.short_button_width)
        col3.addWidget(self.tresetButton)
        col3.addStretch()
        root.addLayout(col3)

        col4 = qt.QVBoxLayout()
        self._add_value_row(col4, "Frequency:", "frequencyValueLabel")
        self._add_value_row(col4, "Amplitude:", "amplitudeValueLabel")
        self._add_value_row(col4, "Offset:", "offsetValueLabel")
        self._add_value_row(col4, "Power:", "powerValueLabel")
        root.addLayout(col4)

        col5 = qt.QVBoxLayout()
        self._add_value_row(col5, "Phase:", "phaseValueLabel", width=40)
        self.phase0Button = qt.QPushButton("> 0 <")
        self.phase0Button.setFixedWidth(self.short_button_width)
        col5.addWidget(self.phase0Button)
        self.phaseResetButton = qt.QPushButton("reset")
        self.phaseResetButton.setFixedWidth(self.short_button_width)
        col5.addWidget(self.phaseResetButton)
        col5.addStretch()
        root.addLayout(col5)

