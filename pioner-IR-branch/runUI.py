from silx.gui import qt
import sys

from pioner_app.ui.mainWindow import mainWindow
from pioner_app.ui.localization import choose_language, set_language
from pioner_app.core.settings import settings

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
    selected_language = choose_language(getattr(settings, "ui_language", "en"))
    set_language(selected_language)
    if selected_language != getattr(settings, "ui_language", "en"):
        settings.save_ui_language(selected_language)
    example = mainWindow()
                # disable UI
    example.experimentBox.setEnabled(False)
    example.mainTabWidget.setEnabled(False)
    example.show()
    app.exec()

    

if __name__ == "__main__":
    pioner_run_ui()
