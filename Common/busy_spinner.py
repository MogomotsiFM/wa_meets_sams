from functools import wraps
from pyqtspinner import WaitingSpinner

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

def busy_spinner(func):
    @wraps(func)
    def wrapper(*args):
        args[0].sender().blockSignals(True)
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = func(*args)
        finally:
            args[0].sender().blockSignals(False)
            QApplication.restoreOverrideCursor()
        return result
    return wrapper


