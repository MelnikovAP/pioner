from silx.gui.qt import QMessageBox


# TODO: use this class as a base one for all classes below
class MessageBox(QMessageBox):
    def __init__(self,
                 title: str,
                 text: str,
                 parent=None):
        super().__init__(parent)
        # self.text = text


class ErrorWindow(QMessageBox):
    def __init__(self, error_text: str, parent=None):
        super().__init__(parent)
        self.setText(error_text)
        self.setWindowTitle("Error")
        self.setIcon(QMessageBox.Critical)
        self.addButton(QMessageBox.Ok)
        self.exec()


class MessageWindow(QMessageBox):
    def __init__(self, message_text: str, parent=None):
        super().__init__(parent)
        self.setText(message_text)
        self.setWindowTitle("Sorry...")
        self.setIcon(QMessageBox.Information)
        self.addButton(QMessageBox.Ok)
        self.exec()


class YesCancelWindow(QMessageBox):
    def __init__(self, message_text: str, parent=None):
        super().__init__(parent)
        self.setText(message_text)
        self.setWindowTitle("Warning")
        self.setIcon(QMessageBox.Warning)
        self.addButton(QMessageBox.Yes)
        self.addButton(QMessageBox.Cancel)
