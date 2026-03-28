import sys

from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QMessageBox
from PyQt5.QtWidgets import QLineEdit, QPushButton, QLabel

from Presenter.presenter import Presenter, LoginStatus

from Common.busy_spinner import busy_spinner

class Login(QDialog):
    def __init__(self, parent, presenter: Presenter):
        super().__init__(parent)

        self.presenter = presenter
        
        self.setStyleSheet("font: 75 12pt Arial;")

        self.setWindowTitle("Login")
        self.resize(350, 115)

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

        self.setModal(True)

        self.initUI()


    def initUI(self):
        self.login_btn.clicked.connect(self.on_login_btn_clicked)
        self.cancel_login_btn.clicked.connect(self.on_cancel_login_clicked)


    def closeEvent(self, event):
        self.presenter.cancel_login()

        event.accept()


    def on_cancel_login_clicked(self):
        self.close()


    def on_login_btn_clicked(self, btn_status):
        username = self.username_text.text()
        password = self.password_text.text()

        print("Username: ", username, "  Password: ", password)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        status, msg = self.presenter.login(username, password)
        QApplication.restoreOverrideCursor()

        print("Login message: ", msg)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Login update")
        msg_box.setText(msg)
        
        match status:
            case LoginStatus.SUCCESS:
                msg_box.setIcon(QMessageBox.Icon.Information)
            case LoginStatus.FAILURE:
                msg_box.setIcon(QMessageBox.Icon.Warning)
            case _:
                msg_box.setIcon(QMessageBox.Icon.Critical)

        x = msg_box.exec_()

        print("Message: ", msg, "  Return value: ", x)
        if status == LoginStatus.SUCCESS:
            self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # We have not tested creating the Presenter here!!!!
    presenter_ = Presenter("path")

    window = Login(None, presenter_)
    window.show()
    sys.exit(app.exec_())