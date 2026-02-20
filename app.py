import os
import sys
import logging

sys.coinit_flags = 2

from PyQt5.QtWidgets import QApplication

from View.gui import MainWindow

from Common.report_printer import ReportPrinter

from Presenter.presenter import Presenter

from Common.log_handler import QLogHandler

logger = QLogHandler()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("debug2.log", mode="w"),
        logging.StreamHandler(stream=sys.stdout),
        logger]
)

sams_path = os.path.join("C:\\", "Users", "GAME", "Desktop", "EdusolSAMS")

presenter = Presenter(sams_path)
printer = ReportPrinter(presenter)

app = QApplication(sys.argv)
window = MainWindow(presenter, printer, logger)
window.show()

sys.exit(app.exec_())