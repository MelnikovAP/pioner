from silx.gui import qt

import sys
sys.path.append('./')
from mainWindow import mainWindow



def create_GUI():
    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = mainWindow()
    example.show()
    app.exec()

if __name__ == "__main__":
    create_GUI()