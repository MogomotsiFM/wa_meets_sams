import sys
import logging

from itertools import takewhile

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QComboBox
from PyQt5.QtWidgets import QPushButton, QLabel

from Common.busy_spinner import busy_spinner

from Presenter.presenter import Presenter


class Config(QDialog):
    def __init__(self, parent, presenter: Presenter):
        super().__init__(parent)

        self.presenter = presenter

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Settings")
        self.resize(400, 190)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        main_layout.addSpacing(2)

        placeholder = "abc"

        #-----
        layout = QHBoxLayout()
        year_label = QLabel("Year:")
        
        layout.addWidget(year_label)

        self.years = QComboBox()
        self.years.setEditable(False)
        years = self.presenter.get_years_list()
        self.years.addItems(years)
        layout.addWidget(self.years)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        grade_label = QLabel("Grade(s):")
        layout.addWidget(grade_label)

        self.grades = QComboBox()
        self.grades.setEditable(False)
        self.grades.setPlaceholderText(placeholder)
        grades = self.presenter.get_grades_list()
        self.grades.addItems(grades)
        layout.addWidget(self.grades)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        layout.addWidget( QLabel("Room(s)") )

        self.rooms = QComboBox()
        self.rooms.setEditable(False)
        self.rooms.setPlaceholderText(placeholder)
        layout.addWidget(self.rooms)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        cycle = QLabel("Assesment Cycle:")
        layout.addWidget(cycle)

        self.cycles = QComboBox()
        self.cycles.setEditable(False)
        self.cycles.setPlaceholderText(placeholder)
        layout.addWidget(self.cycles)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        format = QLabel("Report Format")
        layout.addWidget(format)

        self.formats = QComboBox()
        self.formats.setEditable(False)
        self.formats.setPlaceholderText(placeholder)
        layout.addWidget(self.formats)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        layout = QHBoxLayout()
        self.cancel_printing_btn = QPushButton("Cancel")
        layout.addWidget(self.cancel_printing_btn)
        
        self.send_reports_btn = QPushButton("Send Reports")
        self.send_reports_btn.setEnabled(False)
        layout.addWidget(self.send_reports_btn)

        main_layout.addLayout(layout)

        main_layout.addStretch(2)

        self.setFixedSize(self.size())

        self.setModal(True)

        self.initUI()

        # 
        self.controls = [self.years, self.grades, self.rooms, self.cycles, self.formats]
        self.reset(self.years)


    def initUI(self):
        self.years.activated.connect(self.on_year_selected)
        self.years.currentIndexChanged.connect(self.on_year_selected)
        self.grades.activated.connect(self.on_grade_selected)
        self.rooms.activated.connect(self.on_room_selected)
        self.cycles.activated.connect(self.on_cycle_selected)
        self.formats.activated.connect(self.on_format_selected)
        self.send_reports_btn.clicked.connect(self.on_send_reports)
        self.cancel_printing_btn.clicked.connect(self.on_cancel_btn_clicked)


    def showEvent(self, event):
        super().showEvent(event)
        # Window is now shown and ready

        QTimer.singleShot(500, self.sync)


    def sync(self):
        self.years.setCurrentIndex(0)
        self.grades.setCurrentIndex(0)


    def reset(self, start: QComboBox):
        cs = takewhile(lambda c: c != start, reversed(self.controls))
        for c in cs:
            c.setCurrentText(c.placeholderText())
            c.setEnabled(False)
        start.setEnabled(True)
        self.send_reports_btn.setEnabled(False)


    @busy_spinner
    def on_year_selected(self, current_index):
        year = self.years.currentText()
        is_successful, msg = self.presenter.select_year(year)

        if is_successful:
            grades = self.presenter.get_grades_list()
            self.grades.clear()
            self.grades.addItems(grades)
        else:
            # Open a dialog to surface the error to the user
            msg = msg.capitalize()
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Configuration update")
            msg_box.setText(msg)

            x = msg_box.exec_()

        self.reset(self.years)
        self.grades.setEnabled(True)


    @busy_spinner
    def on_grade_selected(self, current_index):
        grade = self.grades.currentText()
        self.presenter.select_grade(grade)

        rooms = self.presenter.get_rooms_list()
        self.rooms.clear()
        self.rooms.addItems(rooms)

        self.reset(self.grades)
        self.rooms.setEnabled(True)


    @busy_spinner
    def on_room_selected(self, current_index):
        room = self.rooms.currentText()
        self.presenter.select_room(room)

        cycles = self.presenter.get_report_cycles()
        self.cycles.clear()
        self.cycles.addItems(cycles)

        self.reset(self.rooms)
        self.cycles.setEnabled(True)


    @busy_spinner
    def on_cycle_selected(self, current_index):
        cycle = self.cycles.currentText()
        is_successful, msg = self.presenter.select_report_cycle(cycle)

        if is_successful:
            formats = self.presenter.get_report_formats()
            logging.getLogger().debug(f"Report formats: {formats}")
            self.formats.clear()
            self.formats.addItems(formats)

            self.reset(self.cycles)
            self.formats.setEnabled(True)
        else:
            # Open a dialog to surface the error to the user
            msg = msg.capitalize()
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Configuration update")
            msg_box.setText(msg)

            x = msg_box.exec_()

            self.reset(self.years)


    @busy_spinner
    def on_format_selected(self, current_index):
        format = self.formats.currentText()
        self.presenter.select_report_format(format)

        self.send_reports_btn.setEnabled(True)


    def closeEvent(self, event):
        event.accept()


    def on_cancel_btn_clicked(self):
        self.close()


    def on_send_reports(self):
        # Close the config widget returning successfully.
        # Processing is still taking place behind the scenes.
        self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # We have not tested this!!!
    presenter = Presenter("sams_path")

    window = Config(None, presenter)
    window.show()
    sys.exit(app.exec_())