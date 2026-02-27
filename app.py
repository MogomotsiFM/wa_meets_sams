import os
import sys
import logging

from datetime import datetime

sys.coinit_flags = 2

from PyQt5.QtWidgets import QApplication

from View.gui import MainWindow

from Common.directories import create_report_directories
from Common.log_handler import QLogHandler

from Processes.report_printer import ReportPrinter

from Presenter.presenter import Presenter

sams_path = os.path.join("C:\\", "Users", "GAME", "Desktop", "EdusolSAMS")

# Set up directories for reports and cover pages as the current directory of the app.
# The current directory
reports_path = os.path.dirname(os.path.abspath(__file__))

logger = QLogHandler()
log_file = os.path.join(reports_path, "debug.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode="w"),
        logging.StreamHandler(stream=sys.stdout),
        logger]
)

app_dirs = create_report_directories(sams_path, reports_path)

presenter = Presenter(app_dirs)
printer = ReportPrinter(presenter)

app = QApplication(sys.argv)
window = MainWindow(app_dirs, presenter, printer, logger)
window.show()

sys.exit(app.exec_())