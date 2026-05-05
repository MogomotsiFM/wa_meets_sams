import os
import sys
import time
import shutil
import logging

from pathlib import Path

from datetime import datetime

from PyQt5.QtCore import Qt, QThread, QDateTime
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView
from PyQt5.QtWidgets import QLineEdit, QPushButton, QLabel, QGroupBox, QFileDialog, QTabWidget

import qtawesome as qta

from .login import Login
from .options import Config
from .db_selection_widget import DbSelection
from .workflow_config import WorkflowConfig
from .progress_tracker import ProgressReport
from .cover_pgs_table import CoverPagesTable

from Processes.report_printer import ReportPrinter
from Processes.qprocess_incoming_messages import QIncomingMessagesProcessor as Qimp

from Common.directories import AppDirectories
from Common.log_handler import QLogHandler
from Common.busy_spinner import busy_spinner

from Presenter.presenter import Presenter

class MainWindow(QMainWindow):
    def __init__(self, 
                 port: int,
                 run_date: datetime,
                 app_dirs: AppDirectories, 
                 presenter_: Presenter, 
                 report_printer: ReportPrinter, 
                 log_handler: QLogHandler,
                 qimp: Qimp
            ):
        super().__init__()

        self.run_date = None
        self.collection_date = None

        self.app_dirs = app_dirs
        self.presenter = presenter_
        self.report_printer = report_printer
        self.log_handler = log_handler
        self.qimp = qimp

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("WhatsApp, SA-SAMS?")
        self.setGeometry(350, 150, 650, 620)

        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)

        header_group = QGroupBox()
        layout = QVBoxLayout()
        header_group.setLayout(layout)
        self.header = QLabel("SA-SAMS meets WhatsApp")
        self.header.setStyleSheet("font: 75 24pt Arial;")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header)

        main_layout = QVBoxLayout()
        self.main_widget.setLayout(main_layout)

        # If we want to upload the report dossier
        text = QLabel(text="Report dossier")
        self.pdf_dossier = QLineEdit()
        self.browse = QPushButton()
        folder_icon = qta.icon('fa6.folder-open', color='black')
        self.browse.setIcon(folder_icon)
        self.browse.setToolTip("Browse for file")
        layout = QHBoxLayout()
        layout.addWidget(text)
        layout.addWidget(self.pdf_dossier)
        layout.addWidget(self.browse)
        self.pdf_group = QGroupBox()
        self.pdf_group.setLayout(layout)

        # Close button group
        layout = QVBoxLayout()
        close_btn_group = QGroupBox()
        close_btn_group.setLayout(layout)
        self.close_button = QPushButton(text="Exit")
        layout.addWidget(self.close_button)

        tab_widget_group = QGroupBox()
        tab = QTabWidget()
        layout = QVBoxLayout()
        tab_widget_group.setLayout(layout)
        layout.addWidget(tab)


        # Application configuration
        self.conf_widget = WorkflowConfig(self, self.app_dirs)
        tab.addTab(self.conf_widget, "Configs")

        # Using the SA-SAMS wrapper
        sams_widget = QWidget()
        tab.addTab(sams_widget, "SA-SAMS")

        self.cover_pgs = CoverPagesTable(self)
        self.cp_group = QGroupBox(title="Cover Page(s)")
        layout = QHBoxLayout()
        self.cp_group.setLayout(layout)
        layout.addSpacing(2)
        layout.addWidget(self.cover_pgs)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addSpacing(0)

        sams_layout = QVBoxLayout()
        sams_widget.setLayout(sams_layout)
        sams_layout.addSpacing(2)
        sams_layout.addWidget(self.pdf_group)
        sams_layout.addSpacing(2)
        sams_layout.addWidget(self.cp_group)
        sams_layout.addSpacing(2)
        self.db_selection_widget = DbSelection(self)
        self.dbsw = self.db_selection_widget
        sams_layout.addWidget(self.db_selection_widget)
        
        header = self.cover_pgs.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents) # Set default for all
        header.setSectionResizeMode(1, QHeaderView.Stretch) 


        main_layout.addSpacing(2)
        main_layout.addWidget(header_group)
        main_layout.addSpacing(2)
        main_layout.addWidget(tab_widget_group)
        main_layout.addSpacing(2)
        main_layout.addWidget(close_btn_group)
        main_layout.addSpacing(2)

        self.main_widget.adjustSize()
        self.setFixedSize(self.size())

        self.initUI()


    def initUI(self):
        self.dbsw.network_db_radio.clicked.connect(self.on_network_radio_clicked)
        self.dbsw.local_db_radio.clicked.connect(self.on_local_radio_clicked)
        self.dbsw.browse_btn.clicked.connect(self.open_file_dialog)

        self.dbsw.local_continue_login_btn.clicked.connect(self.on_continue_btn_clicked)
        self.dbsw.network_continue_btn.clicked.connect(self.on_continue_btn_clicked)
        self.dbsw.copy_local_db_checkbox.clicked.connect(self.on_copy_db_checkbox_clicked)

        self.dbsw.network_db_path.textChanged.connect(self.on_networked_db_path_updated)
        self.dbsw.network_db_path.textEdited.connect(self.on_networked_db_path_updated)

        self.dbsw.local_db_list.itemClicked.connect(self.on_local_db_selected)
        self.dbsw.local_db_list.itemDoubleClicked.connect(self.on_continue_btn_clicked)

        self.close_button.clicked.connect(self.on_close_clicked)

        # Find the report dossier(s)
        self.browse.clicked.connect(self.on_find_reports_dossiers)

        self.conf_widget.upload.clicked.connect(self.on_reports_selected)
        self.conf_widget.generate.clicked.connect(self.on_reports_selected)

        self.conf_widget.emblem_edit.textChanged.connect(self.on_emblem_path_changed)

        self.conf_widget.dead_date.dateChanged.connect(self.on_deadline_date_time_changed)
        self.conf_widget.dead_time.timeChanged.connect(self.on_deadline_date_time_changed)

        self.conf_widget.collection_date.dateChanged.connect(self.on_collection_date_time_changed)
        self.conf_widget.collection_time.timeChanged.connect(self.on_collection_date_time_changed)


    def delete_thread(self, thread: QThread):
        thread.quit()
        thread.wait()
        thread.deleteLater()


    def sync(self):
        self.dbsw.local_db_radio.click()

        self.dbsw.copy_local_db_checkbox.click()

        if self.presenter.use_local_db_radio_state():
            self.dbsw.local_db_radio.click()
        else:
            self.dbsw.network_db_radio.click()

        self.conf_widget.upload.click()


    def showEvent(self, event):
        super().showEvent(event)
        # Window is now shown and ready

        self.sync()


    @busy_spinner
    def closeEvent(self, event):
        if self.presenter.is_running():
            try:
                self.presenter.report_printing_done()
            except Exception as exp:
                logging.getLogger().debug("The pywinauto controller could not backtrack from the report-printing widget.")
            finally:
                self.presenter.exit_mainwindow()
        event.accept()


    @busy_spinner
    def on_close_clicked(self, _):
        self.close()


    def on_emblem_path_changed(self, txt):
        self.app_dirs.school_emblem_path = txt


    def on_reports_selected(self):
        enable = self.sender() == self.conf_widget.upload
        self.pdf_group.setEnabled(enable)
        self.cp_group.setEnabled(enable)


    def on_deadline_date_time_changed(self):
        d = self.conf_widget.dead_date.date()
        t = self.conf_widget.dead_time.time()
        dt = QDateTime(d, t)
        self.run_date = dt.toPyDateTime()


    def on_collection_date_time_changed(self):
        d = self.conf_widget.collection_date.date()
        t = self.conf_widget.collection_time.time()
        dt = QDateTime(d, t)
        self.collection_date = dt.toPyDateTime()


    def open_file_dialog(self):
        # The getOpenFileName returns a tuple, we only need the file name (the first element)
        file_name, _ = QFileDialog.getOpenFileName(self, 'Open File', '/', "All Files (*.*);;Python Files (*.py)")
        
        if file_name:
            self.dbsw.network_db_path.setText(file_name)
            self.dbsw.network_continue_btn.setEnabled(True)


    def on_find_reports_dossiers(self):
        # The getOpenFileName returns a tuple, we only need the file name (the first element)
        files, _ = QFileDialog.getOpenFileNames(self, 'Open File', '/', "All Files (*.*);;Python Files (*.py)")
        if len(files):
            fs = ";".join(files)
            self.pdf_dossier.setText(fs)


    def on_networked_db_path_updated(self):
        path = self.dbsw.network_db_path.text()
        self.app_dirs.db_path = path

        self.presenter.set_networked_db(path)

        self.dbsw.network_continue_btn.setEnabled(True)


    def on_local_db_selected(self):
        self.dbsw.local_continue_login_btn.setEnabled(True)
        
        db_name = self.dbsw.local_db_list.selectedItems()
        db_name = db_name[0].text()

        self.presenter.select_local_db(db_name)

        # Assume that the database is in the Data folder of the SAMS installation directory
        self.app_dirs.db_path = os.path.join(self.presenter.home_directory(), "Data", f"{db_name}.mdb")


    def on_network_radio_clicked(self):
        self.dbsw.stacked_widget.setCurrentWidget(self.dbsw.network_db_widget)
        self.dbsw.db_group.setTitle("Option B: Database on a networked computer")

        self.dbsw.network_continue_btn.setEnabled(False)

        self.presenter.use_networked_db()

        db_path = self.presenter.last_used_networked_db()

        self.dbsw.network_db_path.setText(db_path)


    def on_local_radio_clicked(self):
        self.dbsw.stacked_widget.setCurrentWidget(self.dbsw.local_db_widget)
        self.dbsw.db_group.setTitle("Option A: Databases on this computer")

        self.dbsw.local_continue_login_btn.setEnabled(False)
        
        self.presenter.use_local_db()

        dbs = self.presenter.local_dbs_list()
        self.dbsw.local_db_list.clear()
        self.dbsw.local_db_list.addItems(dbs)


    def on_copy_db_checkbox_clicked(self):
        desired_state = self.dbsw.copy_local_db_checkbox.checkState()>0
        self.presenter.copy_db_before_opening(int(desired_state))


    def configure_report_printer(self):
        config = Config(self, self.presenter)

        x = config.exec_()
        # Returns 0 if the config dialog was cancelled.
        if x == QDialog.DialogCode.Accepted:
            # Open a progress tracking widget
            pr = ProgressReport(self, self.run_date, self.app_dirs, self.report_printer, self.log_handler)

            x = pr.exec_()
            if x == QDialog.DialogCode.Rejected:
                self.disable_controls()
        else: #
            self.disable_controls()


    def disable_controls(self):
        self.dbsw.local_continue_login_btn.disconnect()
        self.dbsw.local_continue_login_btn.clicked.connect(self.configure_report_printer)

        self.dbsw.network_continue_btn.disconnect()
        self.dbsw.network_continue_btn.clicked.connect(self.configure_report_printer)

        self.dbsw.local_db_radio.setEnabled(False)
        self.dbsw.network_db_radio.setEnabled(False)

        # self.local_db_widget.setEnabled(False)
        self.dbsw.copy_local_db_checkbox.setEnabled(False)
        self.dbsw.local_db_list.setEnabled(False)

        # self.network_db_widget.setEnabled(False)
        self.dbsw.browse_btn.setEnabled(False)


    def on_continue_btn_clicked(self):
        self.app_dirs.cover_pgs_paths = self.cover_pgs.get_cover_pages()

        self.qimp.start(self.run_date, self.collection_date)
        time.sleep(5)

        if self.conf_widget.upload.isChecked():
            self.uploaded_on_continue_btn_clicked()
        else:
            self.generated_on_continue_btn_clicked()


    def generated_on_continue_btn_clicked(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.presenter.continue_to_login()
        QApplication.restoreOverrideCursor()

        login = Login(self, self.presenter)

        # Returns 1 if the dialog was closed with OK. Returns 0 otherwise.
        if login.exec_() == QDialog.DialogCode.Accepted:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.presenter.go_to_progress_report_widget()
            QApplication.restoreOverrideCursor()

            self.configure_report_printer()


    def uploaded_on_continue_btn_clicked(self):
        for file in self.pdf_dossier.text().split(";"):
            logging.getLogger().info(f"Copying {Path(file).name} report dossier to {self.app_dirs.reports_dir}")
            shutil.copy(file, self.app_dirs.reports_dir)

        self.app_dirs.cover_pgs_dir = ""

        logging.getLogger().info(f"DB Location: {self.app_dirs.db_path}")
        process = ProgressReport(
            parent=self, 
            run_date=self.run_date, 
            app_dirs=self.app_dirs, 
            printer=None, 
            log_handler=self.log_handler
        )
        process.exec_()


def main():
    sams_path = os.path.join("C:\\", "Users", "GAME", "Desktop", "EdusolSAMS")
    
    presenter_ = Presenter(sams_path)

    app = QApplication(sys.argv)
    window = MainWindow(presenter_)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()