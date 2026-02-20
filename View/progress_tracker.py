import logging

from PyQt5.QtWidgets import QDialog, QPlainTextEdit
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from PyQt5.QtWidgets import QPushButton

from Common.report_printer import ReportPrinter
from Common.log_handler import QLogHandler

from Presenter.presenter import Presenter

class ProgressReport(QDialog):
    def __init__(self, parent, presenter: Presenter, printer: ReportPrinter):
        super().__init__(parent)

        self.presenter = presenter
        self.printer = printer

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Progress report")
        self.resize(550, 650)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        main_layout.addSpacing(2)
        
        self.edit = QPlainTextEdit()
        self.edit.setReadOnly(True)
        #self.edit.setMaximumBlockCount(500)
        main_layout.addWidget(self.edit)

        main_layout.addSpacing(2)

        layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        layout.addWidget(self.cancel_btn)

        self.close_btn = QPushButton("Close")
        layout.addWidget(self.close_btn)

        main_layout.addLayout(layout)

        main_layout.addSpacing(2)

        self.setFixedSize(self.size())
        self.setModal(True)

        logs = QLogHandler()
        logging.getLogger().addHandler(logs)
        logs.emitter.log.connect(self.edit.appendPlainText)

        self.initUI()


    def initUI(self):
        self.cancel_btn.clicked.connect(self.on_cancel_btn_clicked)


    def showEvent(self, event):
        super().showEvent(event)
        # Window is now shown and read

        self.printer.start()


    def closeEvent(self, event):
        if self.printer.isRunning():
            self.printer.requestInterruption()

            self.printer.wait()

        event.accept()


    def on_cancel_btn_clicked(self):
        self.close()

        



        

