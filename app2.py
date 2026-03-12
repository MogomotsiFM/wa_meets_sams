import asyncio
import uvicorn

from Server.server import run
from Server import server

from Processes import process_incoming_messages as pim

import dotenv
dotenv.load_dotenv()


async def upload_files():
    from redis.asyncio import Redis
    r = await Redis.from_url("redis://localhost")

    await asyncio.sleep(45)

    img_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\school_emblem.png"
    await r.publish("pending_delivery_filenames", img_path)
    
    await asyncio.sleep(2)

    #file_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\Mogomotsi KEAIKITSE - Tel0731948818 - EMailamg.seiphemo@gmail.com.pdf"
    file_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\Mogomotsi KEAIKITSE - Tel0710491875Tel0731948818 - EMailamg.seiphemo@gmail.com.pdf"
    await r.publish("pending_delivery_filenames", file_path)

    await asyncio.sleep(2)
    
    file_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\Segomotsi KEAIKITSE - Tel27731948818 - EMailamg.seiphemo@gmail.com.pdf"
    await r.publish("pending_delivery_filenames", file_path)
    

async def run_helper(port):
    uvi = lambda: uvicorn.run("Server.server:app", port=port)
    await asyncio.gather(
        pim.process_messages(),
        asyncio.to_thread(uvi),
        upload_files()
    )


def run(port):
    asyncio.run(run_helper(port))

if __name__ == "__main__":
    # Run redis on a docker instance
    # docker run -d --name my-redis -p 6379:6379 redis:latest
    import json
    d = {
        "upload_id":"1234567", 
        "file_path":"data/path.png", 
        "send_retries":0
    }
    print(f"Data: {json.dumps(d)}")
    run(4001)