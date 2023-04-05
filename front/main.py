import sys
from silx.gui import qt
from mainWindow import MainWindow


def create_gui():
    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler  # TODO: check what is it
    app.setStyle('Fusion')
    example = MainWindow()
    example.show()
    app.exec()


if __name__ == "__main__":
    create_gui()
