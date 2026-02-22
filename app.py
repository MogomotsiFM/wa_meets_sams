import os
import sys
import logging

from datetime import datetime

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

# Set up directories for reports and cover pages as the current directory of the app.
# The current directory
reports_path = os.path.dirname(os.path.abspath(__file__))

date = f"{datetime.now()}"
date = date.replace(":", "T")
cover_pg_path = os.path.join(reports_path, "Reports", date, "covers")
report_path = os.path.join(reports_path, "Reports", date, "reports")
os.makedirs(name=cover_pg_path, exist_ok=True)
os.makedirs(name=report_path, exist_ok=True)

presenter = Presenter(sams_path, cover_pg_path, report_path)
printer = ReportPrinter(presenter)

app = QApplication(sys.argv)
window = MainWindow(presenter, printer, logger)
window.show()

sys.exit(app.exec_())