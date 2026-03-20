import os
import time
import asyncio
import signal
import logging
import subprocess

import uvicorn

from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSlot
from PyQt5.QtCore import pyqtSignal as Signal

import redis.asyncio as redis

from Processes import process_incoming_messages as pim

PENDING_DELIVERY_FILENAMES = os.getenv("PENDING_DELIVERY_FILENAMES")
UPLOADED_ARTIFACTS = os.getenv("UPLOADED_ARTIFACTS")
OPT_IN_RESPONSES = os.getenv("OPT_IN_RESPONSES")

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")


class QIncomingMessagesProcessor(QThread):
    done = Signal()

    def __init__(self, parent, port: int, run_date: datetime):
        super().__init__(parent)
        self.port = port
        # Two tasks are schedule at this time.
        # Auto-decline opt-in messages. This is required because we need to physically print reports in the dead letter queue.
        # Collate the dead letter queue reports into so they are easier to print.
        self.run_date = run_date
        self.server_proc = None


    async def run_helper(self):
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
        await pim.process_messages(self.run_date)


    async def sp_helper(self):
        r  = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
        await r.publish(PENDING_DELIVERY_FILENAMES, "STOP")
        await r.publish(UPLOADED_ARTIFACTS, "STOP")
        await r.publish(OPT_IN_RESPONSES, "STOP")

    @pyqtSlot()
    def shutdown_processes(self):
        logging.getLogger().info("...Shutting down the FastAPI server...")
        asyncio.run(self.sp_helper())

        os.kill(self.server_proc.pid, signal.SIGTERM)

        self.server_proc.terminate()
        self.server_proc.wait()
        logging.getLogger().info("...FastAPI server was terminated...")


    def run(self):
        asyncio.run(self.run_helper())

        self.done.emit()

