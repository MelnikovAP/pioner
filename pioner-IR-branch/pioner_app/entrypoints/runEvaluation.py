import sys
from silx.gui import qt

from pioner_app.ui.widgets.evaluationWidget import EvaluationWindow


def pioner_run_evaluation():
    app = qt.QApplication.instance() or qt.QApplication([])
    sys.excepthook = qt.exceptionHandler
    app.setStyle('Fusion')
    window = EvaluationWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    pioner_run_evaluation()
