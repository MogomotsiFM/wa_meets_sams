import logging

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QWidget

from .process_pdf import process_reports

from Common.directories import AppDirectories


class QProcessReports(QThread):
    def __init__(self, parent: QWidget, app_dirs: AppDirectories):
        super().__init__(parent)
        self.app_dirs = app_dirs

    def run(self):
        logging.getLogger().info("Starting report processing...")
        try:
            process_reports(
                db_path=self.app_dirs.db_path,
                reports_dir=self.app_dirs.reports_dir,
                cover_pg_dir=self.app_dirs.cover_pgs_dir,
                school_emblem_path=self.app_dirs.school_emblem_path,
                dead_letter_dir=self.app_dirs.dead_letter_dir,
                pending_delivery_dir=self.app_dirs.pending_delivery_dir
            )
        except ValueError as e:
            logging.getLogger().error(f"Error processing reports: {e}")

        except Exception as e:
            logging.getLogger().error(f"Unexpected error processing reports: {e}")
            raise e