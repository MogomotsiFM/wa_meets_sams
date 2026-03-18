import os
import asyncio
import logging

from datetime import datetime, timedelta

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QWidget

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore

from .process_pdf import process_reports, process_dead_letter_queue

from Common.directories import AppDirectories

from dotenv import load_dotenv
load_dotenv()
REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")

class QProcessReports(QThread):
    def __init__(self, parent: QWidget, app_dirs: AppDirectories):
        super().__init__(parent)
        self.app_dirs = app_dirs

    async def generate_report(self):
        jobstores = {
            'default': RedisJobStore(
                host='localhost',
                port=6379,
                db=REDIS_PUBSUB_DB, # Use a specific database number
                jobs_key='apscheduler.jobs', # Custom key for jobs
                run_times_key='apscheduler.run_times' # Custom key for run times
            )
        }
        scheduler = AsyncIOScheduler(jobstores=jobstores)
        scheduler.start()
        
        ct = datetime.now()
        logging.getLogger().debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(minutes=10)
        scheduler.add_job(func=process_dead_letter_queue, args=[self.app_dirs.dead_letter_dir], trigger="date", run_date=run_date)

    def run(self):
        logging.getLogger().info("Starting report processing...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            asyncio.run(
                process_reports(
                    db_path=self.app_dirs.db_path,
                    reports_dir=self.app_dirs.reports_dir,
                    cover_pg_dir=self.app_dirs.cover_pgs_dir,
                    school_emblem_path=self.app_dirs.school_emblem_path,
                    dead_letter_dir=self.app_dirs.dead_letter_dir,
                    pending_delivery_dir=self.app_dirs.pending_delivery_dir
                )
            )
            asyncio.run(self.generate_report())
            logging.getLogger().debug("--------------------------------Done------------------------")
        except ValueError as e:
            logging.getLogger().error(f"Error processing reports: {e}")

        except Exception as e:
            logging.getLogger().error(f"Unexpected error processing reports: {e}")
            raise e
        
