import os
import sys

from PyQt5.QtCore import Qt, QEvent, QThread
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog, QStackedLayout
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QStackedWidget, QCheckBox, QListWidget
from PyQt5.QtWidgets import QLineEdit, QPushButton, QLabel, QListView, QGroupBox, QRadioButton, QFileDialog

from .login import Login
from .options import Config
from .progress_tracker import ProgressReport

from Processes.report_printer import ReportPrinter
from Common.directories import AppDirectories
from Common.log_handler import QLogHandler

from Presenter.presenter import Presenter


class MainWindow(QMainWindow):
    def __init__(self, 
                 app_dirs: AppDirectories, 
                 presenter_: Presenter, 
                 report_printer: ReportPrinter, 
                 log_handler: QLogHandler
            ):
        super().__init__()

        self.app_dirs = app_dirs
        self.presenter = presenter_
        self.report_printer = report_printer
        self.log_handler = log_handler

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("WhatsApp, SA-SAMS?")
        self.setGeometry(350, 150, 650, 450)

        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)

        header_group = QGroupBox()
        layout = QVBoxLayout()
        header_group.setLayout(layout)
        self.header = QLabel("SA-SAMS meets WhatsApp")
        self.header.setStyleSheet("font: 75 24pt Arial;")
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.header)

        vert_layout = QVBoxLayout()
        self.main_widget.setLayout(vert_layout)

        # Select database location
        layout = QHBoxLayout()
        db_location_group = QGroupBox(title="Select database location")
        db_location_group.setLayout(layout)
        self.local_db_radio = QRadioButton(text="On this computer")
        self.network_db_radio = QRadioButton(text="On the network")
        layout.addWidget(self.local_db_radio)
        layout.addWidget(self.network_db_radio)
        self.local_db_radio.setChecked(True)
        
        # Select specific database
        self.local_db_widget = QWidget()
        self.network_db_widget = QWidget()

        self.stacked_widget = QStackedWidget()

        layout = QVBoxLayout()
        self.db_group = QGroupBox(title="Option A: Databases on this computer")
        self.db_group.setLayout(layout)
        self.stacked_widget.addWidget(self.local_db_widget)
        self.stacked_widget.addWidget(self.network_db_widget)
        layout.addWidget(self.stacked_widget)

        # Local DB controls
        layout = QVBoxLayout()
        self.local_db_widget.setLayout(layout)

        self.copy_local_db_checkbox = QCheckBox(text="Copy database before opening")
        self.local_db_list = QListWidget()
        self.local_continue_login_btn = QPushButton(text="Continue")
        self.local_continue_login_btn.setEnabled(False)
        layout.addWidget(self.copy_local_db_checkbox)
        layout.addWidget(self.local_db_list)
        layout.addWidget(self.local_continue_login_btn)

        # Networked DB controls
        layout = QVBoxLayout()
        self.network_db_widget.setLayout(layout)

        self.network_db_path = QLineEdit()
        self.network_db_path.setReadOnly(True)
        
        self.browse_btn = QPushButton(text="Browse...")
        self.network_continue_btn = QPushButton(text="Continue")
        self.network_continue_btn.setEnabled(False)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.network_db_path)
        hlayout.addWidget(self.browse_btn)
        
        layout.addLayout(hlayout)
        layout.addWidget(self.network_continue_btn)
        layout.addStretch(2)

        # Close button group
        layout = QVBoxLayout()
        close_btn_group = QGroupBox()
        close_btn_group.setLayout(layout)
        self.close_button = QPushButton(text="Exit")
        layout.addWidget(self.close_button)

        vert_layout.addSpacing(2)
        vert_layout.addWidget(header_group)
        vert_layout.addSpacing(2)
        vert_layout.addWidget(db_location_group)
        vert_layout.addSpacing(2)
        vert_layout.addWidget(self.db_group)
        vert_layout.addSpacing(2)
        vert_layout.addWidget(close_btn_group)
        vert_layout.addSpacing(2)

        self.main_widget.adjustSize()
        self.setFixedSize(self.size())

        self.initUI()


    def initUI(self):
        self.network_db_radio.clicked.connect(self.on_network_radio_clicked)
        self.local_db_radio.clicked.connect(self.on_local_radio_clicked)
        self.browse_btn.clicked.connect(self.open_file_dialog)

        self.local_continue_login_btn.clicked.connect(self.on_continue_btn_clicked)
        self.network_continue_btn.clicked.connect(self.on_continue_btn_clicked)
        self.copy_local_db_checkbox.clicked.connect(self.on_copy_db_checkbox_clicked)

        self.network_db_path.textChanged.connect(self.on_networked_db_path_updated)
        self.network_db_path.textEdited.connect(self.on_networked_db_path_updated)

        self.local_db_list.itemClicked.connect(self.on_local_db_selected)
        self.local_db_list.itemDoubleClicked.connect(self.on_continue_btn_clicked)

        self.close_button.clicked.connect(self.on_close_clicked)


    def sync(self):
        self.local_db_radio.click()

        self.copy_local_db_checkbox.click()

        if self.presenter.use_local_db_radio_state():
            self.local_db_radio.click()
        else:
            self.network_db_radio.click()


    def showEvent(self, event):
        super().showEvent(event)
        # Window is now shown and ready

        self.sync()


    def closeEvent(self, event):
        if self.presenter.is_running():
            try:
                self.presenter.report_printing_done()
            finally:
                self.presenter.exit_mainwindow()

        event.accept()


    def on_close_clicked(self):
        self.close()


    def open_file_dialog(self):
        # The getOpenFileName returns a tuple, we only need the file name (the first element)
        file_name, _ = QFileDialog.getOpenFileName(self, 'Open File', '/', "All Files (*.*);;Python Files (*.py)")
        
        if file_name:
            self.network_db_path.setText(file_name)

            self.network_continue_btn.setEnabled(True)


    def on_networked_db_path_updated(self):
        path = self.network_db_path.text()
        self.app_dirs.db_path = path

        self.presenter.set_networked_db(path)

        self.network_continue_btn.setEnabled(True)


    def on_local_db_selected(self):
        self.local_continue_login_btn.setEnabled(True)
        
        db_name = self.local_db_list.selectedItems()
        db_name = db_name[0].text()

        self.presenter.select_local_db(db_name)

        # Assume that the database is in the Data folder of the SAMS installation directory
        self.app_dirs.db_path = os.path.join(self.presenter.home_directory(), "Data", f"{db_name}.mdb")


    def on_network_radio_clicked(self):
        self.stacked_widget.setCurrentWidget(self.network_db_widget)
        self.db_group.setTitle("Option B: Database on a networked computer")

        self.network_continue_btn.setEnabled(False)

        self.presenter.use_networked_db()

        db_path = self.presenter.last_used_networked_db()

        self.network_db_path.setText(db_path)


    def on_local_radio_clicked(self):
        self.stacked_widget.setCurrentWidget(self.local_db_widget)
        self.db_group.setTitle("Option A: Databases on this computer")

        self.local_continue_login_btn.setEnabled(False)
        
        self.presenter.use_local_db()

        dbs = self.presenter.local_dbs_list()
        self.local_db_list.clear()
        self.local_db_list.addItems(dbs)


    def on_copy_db_checkbox_clicked(self):
        desired_state = self.copy_local_db_checkbox.checkState()>0
        self.presenter.copy_db_before_opening(int(desired_state))


    def configure_report_printer(self):
        config = Config(self, self.presenter)

        x = config.exec_()
        # Returns 0 if the config dialog was cancelled.
        if x == QDialog.DialogCode.Accepted:
            # Open a progress tracking widget
            pr = ProgressReport(self, self.app_dirs, self.presenter, self.report_printer, self.log_handler)

            x = pr.exec_()
            if x == QDialog.DialogCode.Rejected:
                self.disable_controls()
        else: #
            self.disable_controls()


    def disable_controls(self):
        self.local_continue_login_btn.disconnect()
        self.local_continue_login_btn.clicked.connect(self.configure_report_printer)

        self.network_continue_btn.disconnect()
        self.network_continue_btn.clicked.connect(self.configure_report_printer)

        self.local_db_radio.setEnabled(False)
        self.network_db_radio.setEnabled(False)

        # self.local_db_widget.setEnabled(False)
        self.copy_local_db_checkbox.setEnabled(False)
        self.local_db_list.setEnabled(False)

        # self.network_db_widget.setEnabled(False)
        self.browse_btn.setEnabled(False)


    def on_continue_btn_clicked(self):
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


def main():
    sams_path = os.path.join("C:\\", "Users", "GAME", "Desktop", "EdusolSAMS")
    
    presenter_ = Presenter(sams_path)

    app = QApplication(sys.argv)
    window = MainWindow(presenter_)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()