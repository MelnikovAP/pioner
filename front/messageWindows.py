from silx.gui import qt

class ErrorWindow(qt.QMessageBox):
    def __init__(self, error_text: str, parent=None):
        super(ErrorWindow, self).__init__(parent)
        self.setText(error_text)
        self.setWindowTitle("Error")
        self.setIcon(qt.QMessageBox.Critical)
        self.addButton(qt.QMessageBox.Ok)
        self.exec()

class MessageWindow(qt.QMessageBox):
    def __init__(self, message_text: str, parent=None):
        super(MessageWindow, self).__init__(parent)
        self.setText(message_text)
        self.setWindowTitle("Sorry...")
        self.setIcon(qt.QMessageBox.Information)
        self.addButton(qt.QMessageBox.Ok)
        self.exec()

class YesCancelWindow(qt.QMessageBox):
    def __init__(self, message_text: str, parent=None):
        super(YesCancelWindow, self).__init__(parent)
        self.setText(message_text)
        self.setWindowTitle("Warning")
        self.setIcon(qt.QMessageBox.Warning)
        self.addButton(qt.QMessageBox.Yes)
        self.addButton(qt.QMessageBox.Cancel)