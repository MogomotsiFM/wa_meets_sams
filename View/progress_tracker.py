import logging

from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSlot as Slot
from PyQt5.QtWidgets import QDialog, QPlainTextEdit
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from PyQt5.QtWidgets import QPushButton

from Common.directories import AppDirectories
from Common.log_handler import QLogHandler

from Processes.report_printer import ReportPrinter
from Processes.qprocess_pdf import QProcessReports

class ProgressReport(QDialog):
    def __init__(self,
                 parent,
                 run_date: datetime,
                 app_dirs:AppDirectories, 
                 printer: ReportPrinter, 
                 log_handler: QLogHandler
            ):
        super().__init__(parent)

        self.run_date = run_date
        self.app_dirs = app_dirs
        self.printer = printer
        self.log_handler = log_handler

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Progress report")
        self.resize(850, 650)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        main_layout.addSpacing(2)
        
        self.edit = QPlainTextEdit()
        self.edit.setReadOnly(True)
        self.edit.setStyleSheet("font: 75 10pt Arial;")
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

        self.processor = QProcessReports(self, self.app_dirs, self.run_date)

        self.initUI()


    def initUI(self):
        self.cancel_btn.clicked.connect(self.on_cancel_btn_clicked)

        self.log_handler.emitter.log.connect(self.append_and_scroll_scrollbar)

        #fn = lambda : self.delete_thread(self.processor)
        #self.processor.done.connect(fn)
        
        if self.printer:
            self.printer.finished.connect(self.processor.start)
        else:
            self.processor.start()


    def delete_thread(self, thread: QThread):
        thread.quit()
        thread.wait()
        thread.deleteLater()


    @Slot(str)
    def append_and_scroll_scrollbar(self, text):
        self.edit.appendPlainText(text)
        # Get the vertical scroll bar
        scrollbar = self.edit.verticalScrollBar()
        # Set its value to its maximum
        scrollbar.setValue(scrollbar.maximum())


    def showEvent(self, event):
        super().showEvent(event)

        if self.printer:
            self.printer.start()


    def closeEvent(self, event):
        if self.printer and self.printer.isRunning():
            self.printer.requestInterruption()

            self.printer.wait()

        event.accept()


    def on_cancel_btn_clicked(self):
        self.close()

        

