import os
import uuid
import asyncio
import logging

from datetime import datetime

from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QWidget

from PyQt5.QtCore import pyqtSignal as Signal

from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore

import redis.asyncio as redis

from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError, BusyLoadingError

from .process_pdf import process_reports, process_dead_letter_queue

from .process_incoming_messages import auto_decline, done, unsubscribe

from Common.directories import AppDirectories

from dotenv import load_dotenv
load_dotenv()

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")
REDIS_KV_STORE_DB = os.getenv("KV_STORE_DB")

class QProcessReports(QThread):
    done = Signal()


    def __init__(self, parent: QWidget, app_dirs: AppDirectories, run_date: datetime):
        super().__init__(parent)
        self.app_dirs = app_dirs
        self.run_date = run_date


    @staticmethod
    async def shielded_clean_up(dead_letter_dir):
        asyncio.shield(QProcessReports.clean_up(dead_letter_dir))


    @staticmethod
    async def clean_up(dead_letter_dir, reports_dir):
        
        while True:
            try:
                r  = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
                await auto_decline()

                retry_strategy = Retry(ExponentialBackoff(cap=10, base=1), 3)
                kv = await redis.from_url(
                    "redis://localhost", 
                    db=REDIS_KV_STORE_DB, 
                    retry=retry_strategy,
                    retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError, asyncio.exceptions.CancelledError]
                )
                while True:
                    dn = await done(kv, r)
                    logging.getLogger().debug(f"Are we done processing all the messages: {dn}")
                    if dn:
                        break
                    else:
                        await asyncio.sleep(15)
                
                await unsubscribe("STOP", r)
                await process_dead_letter_queue(dead_letter_dir, reports_dir)
                break
            except BaseException as exp:
                logging.getLogger().debug(f"Something threw an asyncio.CancelledError exception: {exp}")
                logging.getLogger().debug("Retrying...")


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
        executors = {
            'default': ThreadPoolExecutor(100),
            'processpool': ProcessPoolExecutor(10)
        }
        job_defaults = {
            "misfire_grace_time": 30*60,
            #"max_instances":1
        }
        scheduler = AsyncIOScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults)
        scheduler.start()
        dead_letter_dir = self.app_dirs.dead_letter_dir
        reports_dir = self.app_dirs.reports_dir
        scheduler.add_job(func="Processes.qprocess_pdf:QProcessReports.clean_up", args=[dead_letter_dir, reports_dir], trigger="date", run_date=self.run_date, id=f"{uuid.uuid4()}")


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
                    cover_pgs=self.app_dirs.cover_pgs_paths,
                    school_emblem_path=self.app_dirs.school_emblem_path,
                    dead_letter_dir=self.app_dirs.dead_letter_dir,
                    pending_delivery_dir=self.app_dirs.pending_delivery_dir
                )
            )
            asyncio.run(self.generate_report())
            logging.getLogger().debug("--------------------------------Done----------------------------------")
        except ValueError as e:
            logging.getLogger().error(f"Error processing reports: {e}")

        except Exception as e:
            logging.getLogger().error(f"Unexpected error processing reports: {e}")
            raise e

        self.done.emit()

