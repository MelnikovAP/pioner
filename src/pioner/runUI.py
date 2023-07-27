from silx.gui import qt
import sys

from pioner.front.mainWindow import mainWindow

def pioner_run_ui():
    """
    Test documentation.

    :param kind: Optional "kind" of ingredients.
    :type kind: list[str] or None
    :raise lumache.InvalidKindError: If the kind is invalid.
    :return: The ingredients list.
    :rtype: list[str]

    """
    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    example = mainWindow()
    example.show()
    app.exec()

if __name__ == "__main__":
    pioner_run_ui()