import os
import time
import asyncio
import signal
import logging
import subprocess

import uvicorn

from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSlot as Slot
from PyQt5.QtCore import pyqtSignal as Signal

import redis.asyncio as redis

from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError, BusyLoadingError

from Processes import process_incoming_messages as pim

PENDING_DELIVERY_FILENAMES = os.getenv("PENDING_DELIVERY_FILENAMES")
UPLOADED_ARTIFACTS = os.getenv("UPLOADED_ARTIFACTS")
OPT_IN_RESPONSES = os.getenv("OPT_IN_RESPONSES")

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")
REDIS_KV_STORE_DB = os.getenv("KV_STORE_DB")

class QIncomingMessagesProcessor(QThread):
    done = Signal()

    def __init__(self, parent, port: int):
        super().__init__(parent)
        self.port = port
        # Two tasks are schedule at this time.
        # Auto-decline opt-in messages. This is required because we need to physically print reports in the dead letter queue.
        # Collate the dead letter queue reports into so they are easier to print.
        self.run_date = None
        self.report_collection_date = None

        # Starting the server on a dedicated process because running it on a thread and shutting
        # it down using ctrl-C shuts down the entire application. This meant we could not shut the 
        # application down cleanly.
        self.server_proc = subprocess.Popen(
            [
                "uvicorn", "Server.server:app", 
                "--host", "127.0.0.1", 
                "--port", f"{self.port}"
            ]
        )


    async def process_messages(self):
        try:
            await pim.process_messages(self.run_date, self.report_collection_date)
        except BaseException as exp:
            logging.getLogger().debug(f"PIM exception: {exp}")
        except Exception as exp:
            logging.getLogger().debug(f"PIM exception: {exp}")


    async def unsubscribe(self):
        await pim.unsubscribe("STOP")
        
        retry_strategy = Retry(ExponentialBackoff(cap=10, base=1), 3)
        kv = await redis.from_url(
            "redis://localhost", 
            db=REDIS_KV_STORE_DB, 
            retry=retry_strategy,
            retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError, asyncio.exceptions.CancelledError]
        )
        while not ( await pim.done(kv) ):
            await asyncio.sleep(15)


    @Slot()
    def shutdown_processes(self):
        logging.getLogger().info("...Shutting down the FastAPI server...")
        asyncio.run(self.unsubscribe())

        # poll() returns None if the process has not been terinated
        if self.server_proc and self.server_proc.poll() is None:
            os.kill(self.server_proc.pid, signal.SIGTERM)

            self.server_proc.terminate()
            self.server_proc.wait()
        logging.getLogger().info("...FastAPI server was terminated...")


    @Slot(datetime)
    def start(self, run_date: datetime, report_collection_date: datetime):
        self.run_date = run_date
        self.report_collection_date = report_collection_date

        super().start()


    def run(self):
        task = asyncio.run(self.process_messages())

        logging.getLogger().info(f"Message processing done")

        self.done.emit()

