from silx.gui import qt
import os
from settings import *
from messageWindows import *
from constants import SETTINGS_FILE_REL_PATH


class configWindow(qt.QDialog):
    def __init__(self, parent=None):
        super(configWindow, self).__init__(parent=parent)

        # ####### UI setup
        # ########################################
        self.setWindowTitle("Help & Configuration")
        self.setFixedHeight(400)
        self.setFixedWidth(300)
        self.setWindowFlag(qt.Qt.WindowContextHelpButtonHint, False)

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
        self.parent().settings.tango_host = self.tangoHostInput.text()
        self.parent().settings.device_proxy = self.deviceProxyInput.text()
        self.parent().settings.http_host = self.httpHostInput.text()

    def load_settings_from_file(self):
        self.parent().load_settings_from_file(fpath=True)
        self.tangoHostInput.setText(self.parent().settings.tango_host)
        self.deviceProxyInput.setText(self.parent().settings.device_proxy)
        self.httpHostInput.setText(self.parent().settings.http_host)

    def save_settings_to_file(self):
        self.parent().save_settings_to_file(fpath=True)
    
    def reset_settings(self):
        self.parent().reset_settings()
        self.tangoHostInput.setText(self.parent().settings.tango_host)
        self.deviceProxyInput.setText(self.parent().settings.device_proxy)
        self.httpHostInput.setText(self.parent().settings.http_host)

if __name__ == "__main__":
    import sys
    app = qt.QApplication(sys.argv)
    example = configWindow()
    example.show()
    sys.exit(app.exec())