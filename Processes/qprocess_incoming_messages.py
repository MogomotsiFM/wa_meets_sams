import asyncio

import uvicorn

from datetime import datetime

from PyQt5.QtCore import QThread

from Processes import process_incoming_messages as pim

class QIncomingMessagesProcessor(QThread):
    def __init__(self, parent, port: int, run_date: datetime):
        super().__init__(parent)
        self.port = port
        # Two tasks are schedule at this time.
        # Auto-decline opt-in messages. This is required because we need to physically print reports in the dead letter queue.
        # Collate the dead letter queue reports into so they are easier to print.
        self.run_date = run_date  

    async def run_helper(self):
        uvi = lambda: uvicorn.run("Server.server:app", port=self.port)
        await asyncio.gather(
            pim.process_messages(self.run_date),
            asyncio.to_thread(uvi),
        )

    def run(self):
        asyncio.run(self.run_helper())