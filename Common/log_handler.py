# https://stackoverflow.com/questions/66664542/conflicting-names-between-logging-emit-function-and-qt-emit-signal/66664679#66664679:~:text=The%20problem%20is%20that%20both%20base%20classes%20have%20an%20emit()%20method%20that%20causes%20that%20collision.%20A%20workaround%20is%20not%20to%20use%20inheritance%20but%20composition%3A

import logging

from PyQt5.QtCore import QObject

from PyQt5.QtCore import pyqtSignal as Signal

from PyQt5.QtWidgets import QPlainTextEdit

class Emitter(QObject):
    log = Signal(str)

#QLogHandler
class QLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self._emitter = Emitter()

    @property
    def emitter(self):
        return self._emitter

    def emit(self, record):
        msg = self.format(record)
        self.emitter.log.emit(msg)


class QTextEditLogger(logging.Handler, QObject):
    appendPlainText = Signal(str)

    def __init__(self):
        super().__init__()
        QObject.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.appendPlainText.emit(msg)