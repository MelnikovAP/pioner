import sys
from silx.gui import qt
from mainWindow import mainWindow
import os

def create_GUI():
    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = mainWindow()
    example.show()
    app.exec()

if __name__ == "__main__":
    create_GUI()