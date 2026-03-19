import os
import sys
import logging

from datetime import datetime, timedelta

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

qlogger = QLogHandler()
log_file = os.path.join(reports_path, "debug.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, mode="w"),
        logging.StreamHandler(stream=sys.stdout),
        qlogger]
)

emblem_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\school_emblem.png"
app_dirs = create_report_directories(sams_path, reports_path, emblem_path)

presenter = Presenter(app_dirs)
printer = ReportPrinter(presenter)

# We have to set a deadline for responses to opt-in messages. 
# We need this because we have to physically print the report in the dead letter queue.
run_date = datetime.now() + timedelta(minutes=30)
app = QApplication(sys.argv)
window = MainWindow(run_date, app_dirs, presenter, printer, qlogger)
window.show()

sys.exit(app.exec_())