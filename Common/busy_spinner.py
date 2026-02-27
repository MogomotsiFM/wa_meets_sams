from functools import wraps
from contextlib import contextmanager

from pyqtspinner import WaitingSpinner

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QObject

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


@contextmanager
def context_mngd_busy_spinner(sender: QObject):
    sender.blockSignals(True)
    QApplication.setOverrideCursor(Qt.WaitCursor)
    yield
    QApplication.restoreOverrideCursor()
    sender.blockSignals(False)
