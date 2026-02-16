import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QDialog
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget, QCheckBox, QMessageBox
from PyQt5.QtWidgets import QLineEdit, QPushButton, QLabel, QListView, QGroupBox, QRadioButton, QFileDialog

class Login(QDialog):
    def __init__(self, parent, presenter):
        super().__init__(parent)

        self.presenter = presenter
        
        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Login")
        self.setGeometry(400, 150, 450, 115)

        main_layout = QVBoxLayout()
        #self.central_widget.setLayout(main_layout)
        self.setLayout(main_layout)

        main_layout.addSpacing(2)

        layout = QHBoxLayout()
        username_label = QLabel("Username:")
        layout.addWidget(username_label)

        self.username_text = QLineEdit()
        layout.addWidget(self.username_text)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        layout = QHBoxLayout()
        password_label = QLabel("Password:")
        layout.addWidget(password_label)

        self.password_text = QLineEdit()
        self.password_text.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_text)

        main_layout.addLayout(layout)
        main_layout.addSpacing(2)

        layout = QHBoxLayout()
        self.cancel_login_btn = QPushButton("Cancel")
        layout.addWidget(self.cancel_login_btn)
        
        self.login_btn = QPushButton("Login")
        layout.addWidget(self.login_btn)

        main_layout.addLayout(layout)

        main_layout.addStretch(2)

        self.setFixedSize(self.size())

    def initUI(self):
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Login(None, "Presenter")
    window.show()
    sys.exit(app.exec_())