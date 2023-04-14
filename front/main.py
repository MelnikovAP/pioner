import os
import sys

from mainWindow import mainWindow
from silx.gui import qt


def create_GUI():
    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = mainWindow()
    example.show()
    app.exec()

if __name__ == "__main__":
    create_GUI()