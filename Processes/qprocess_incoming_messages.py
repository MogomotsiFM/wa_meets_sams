import asyncio

import uvicorn

from PyQt5.QtCore import QThread

from Processes import process_incoming_messages as pim

class QIncomingMessagesProcessor(QThread):
    def __init__(self, parent, port):
        super().__init__(parent)
        self.port = port

    async def run_helper(self):
        uvi = lambda: uvicorn.run("Server.server:app", port=self.port)
        await asyncio.gather(
            pim.process_messages(),
            asyncio.to_thread(uvi),
        )

    def run(self):
        asyncio.run(self.run_helper())