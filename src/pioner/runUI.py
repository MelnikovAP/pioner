from silx.gui import qt
import sys

from pioner.front.mainWindow import mainWindow

def pioner_run_ui():
    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = mainWindow()
    example.show()
    app.exec()

if __name__ == "__main__":
    pioner_run_ui()