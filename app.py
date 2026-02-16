import os
import sys

sys.coinit_flags = 2

from PyQt5.QtWidgets import QApplication

from View.gui import MainWindow

from Presenter import presenter


sams_path = os.path.join("C:\\", "Users", "GAME", "Desktop", "EdusolSAMS")

presenter_ = presenter.Presenter(sams_path)

app = QApplication(sys.argv)
window = MainWindow(presenter_)
window.show()
sys.exit(app.exec_())