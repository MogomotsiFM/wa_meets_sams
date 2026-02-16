import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox
from PyQt5.QtWidgets import QPushButton, QLabel

class Config(QDialog):
    def __init__(self, parent, presenter):
        super().__init__(parent)

        self.presenter = presenter

        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Settings")
        self.setGeometry(400, 150, 500, 175)

        #self.central_widget = QWidget(self)
        #self.setCentralWidget(self.central_widget)

        main_layout = QVBoxLayout()
        #self.central_widget.setLayout(main_layout)
        self.setLayout(main_layout)

        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        year = QLabel("Year:")
        
        layout.addWidget(year)

        self.year = QComboBox()
        self.year.setEditable(False)
        #year.addItems(["A", "B", "C", "D", "E"])
        layout.addWidget(self.year)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        grade = QLabel("Grade:")
        layout.addWidget(grade)

        self.grade = QComboBox()
        self.grade.setEditable(False)
        layout.addWidget(self.grade)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        cycle = QLabel("Assesment Cycle:")
        layout.addWidget(cycle)

        self.cycle = QComboBox()
        self.cycle.setEditable(False)
        layout.addWidget(self.cycle)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        format = QLabel("Report Format")
        layout.addWidget(format)

        self.format = QComboBox()
        self.format.setEditable(False)
        layout.addWidget(self.format)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        #-----
        layout = QHBoxLayout()
        self.cancel_login_btn = QPushButton("Cancel")
        layout.addWidget(self.cancel_login_btn)
        
        self.send_reports_btn = QPushButton("Send Reports")
        layout.addWidget(self.send_reports_btn)

        main_layout.addLayout(layout)

        main_layout.addStretch(2)

        self.setFixedSize(self.size())


    def initUI(self):
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Config(None, "Presenter")
    window.show()
    sys.exit(app.exec_())