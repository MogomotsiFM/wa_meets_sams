import sys

from itertools import takewhile

from PyQt5.QtCore import Qt, QThread
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox
from PyQt5.QtWidgets import QPushButton, QLabel

from .report_printer import ReportPrinter

from Presenter.presenter import Presenter

class Config(QDialog):
    def __init__(self, parent, presenter: Presenter, report_printer: ReportPrinter):
        super().__init__(parent)

        self.presenter = presenter
        self.report_printer = report_printer

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Settings")
        self.setGeometry(400, 150, 400, 190)

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

        #-----
        layout = QHBoxLayout()
        self.cancel_printing_btn = QPushButton("Cancel")
        layout.addWidget(self.cancel_printing_btn)
        
        self.send_reports_btn = QPushButton("Send Reports")
        self.send_reports_btn.setEnabled(False)
        layout.addWidget(self.send_reports_btn)

        main_layout.addLayout(layout)

        main_layout.addStretch(2)

        self.setFixedSize(self.size())

        self.initUI()

        self.sync()

        self.controls = [self.grades, self.rooms, self.cycles, self.formats]

        self.reset(self.years)


    def initUI(self):
        self.years.activated.connect(self.on_year_selected)
        self.grades.activated.connect(self.on_grade_selected)
        self.rooms.activated.connect(self.on_room_selected)
        self.cycles.activated.connect(self.on_cycle_selected)
        self.formats.activated.connect(self.on_format_selected)
        self.send_reports_btn.clicked.connect(self.on_send_reports)
        self.cancel_printing_btn.clicked.connect(self.on_cancel_btn_clicked)


    def sync(self):
        self.years.setCurrentIndex(0)
        self.grades.setCurrentIndex(0)


    def reset(self, start):
        cs = takewhile(lambda c: c != start, reversed(self.controls))
        for c in cs:
            c.setCurrentText(c.placeholderText())
        self.send_reports_btn.setEnabled(False)


    def on_year_selected(self):
        year = self.years.currentText()
        self.presenter.select_year(year)

        self.reset(self.years)


    def on_grade_selected(self):
        grade = self.grades.currentText()
        self.presenter.select_grade(grade)

        rooms = self.presenter.get_rooms_list()
        self.rooms.clear()
        self.rooms.addItems(rooms)

        self.reset(self.grades)


    def on_room_selected(self):
        room = self.rooms.currentText()
        self.presenter.select_room(room)

        cycles = self.presenter.get_report_cycles()
        self.cycles.clear()
        self.cycles.addItems(cycles)

        self.reset(self.rooms)


    def on_cycle_selected(self):
        cycle = self.cycles.currentText()
        self.presenter.select_report_cycle(cycle)

        formats = self.presenter.get_report_formats()
        print("Report formats: ", formats)
        self.formats.clear()
        self.formats.addItems(formats)

        self.reset(self.cycles)


    def on_format_selected(self):
        format = self.formats.currentText()
        self.presenter.select_report_format(format)

        self.send_reports_btn.setEnabled(True)


    def closeEvent(self, event):
        self.presenter.report_printing_done()
        #self.presenter.exit_mainwindow()
        self.presenter.home()

        event.accept()


    def on_cancel_btn_clicked(self):
        self.close()


    def on_send_reports(self):
        grade  = self.grades.currentText()
        room   = self.rooms.currentText()
        cycle  = self.cycles.currentText()
        format = self.formats.currentText()
        self.report_printer.configure(grade, room, cycle, format)
        self.report_printer.run()
        # Close the config widget returning successfully.
        # Processing is still taking place behind the scenes.
        #self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # We have not tested this!!!
    presenter = Presenter("sams_path")

    window = Config(None, presenter, None)
    window.show()
    sys.exit(app.exec_())