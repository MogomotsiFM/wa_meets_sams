import os
import json
import asyncio
import logging
import redis.asyncio as redis

from pathlib import Path

from Messangers.wa_wrapper import WhatsAppWrapper

from dotenv import load_dotenv
load_dotenv()

STOPWORD = "STOP"

logger = logging.getLogger()

def init() -> WhatsAppWrapper:
    WA_SAMS_TOKEN = os.getenv("WA_SAMS_TOKEN")
    WA_SAMS_PHONE_ID = os.getenv("WA_SAMS_PHONE_ID")
    if WA_SAMS_TOKEN is None or WA_SAMS_PHONE_ID is None:
        raise ValueError("WA_SAMS_TOKEN and WA_SAMS_PHONE_ID environment variables should be set.")
    
    messanger = WhatsAppWrapper(bearer_token=WA_SAMS_TOKEN, phone_number_id=WA_SAMS_PHONE_ID)
    logger.debug(f"(NoName)  token: {WA_SAMS_TOKEN}")
    logger.debug(f"(NoName)  Phone Id: {WA_SAMS_PHONE_ID}")

    return messanger


async def reader(channel: redis.client.PubSub):
    messanger = init()
    while True:
        message = await channel.get_message(ignore_subscribe_messages=True, timeout=None)
        if message is not None:
            json_msg = message["data"].decode()
            logger.info(f"(Reader) Message recieved: {json_msg}")
            if json_msg == STOPWORD:
                logger.info("(Reader) STOP")
                break
            await process_message(messanger, json_msg)
        logger.info("(Reader) Nothing to do...")
        await asyncio.sleep(1)


async def process_message(messanger, body_bytes):
    body = json.loads(body_bytes)
    entries = body["entry"]
    entry = entries[0]
    changes = entry["changes"]
    change = changes[0]
    value = change["value"]
    msgs = value["messages"]
    for msg in msgs:
        # Send read message
        m = msg["text"]
        #asyncio.sleep(1)
        # Reply to the message
        img_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\school_emblem.png"
        upload_re = await messanger.upload(img_path)
        logger.info(f"(Reader)  Upload response: {upload_re}")
        #response = await self.messanger.send_opt_in_message(msg["from"], date="March 6", weekday="Friday", time="10.30am")
        #logger.debug(f"(Reader)  Response from sending opt in message: {response}")


async def process_messages():
    r = await redis.from_url("redis://localhost")
    async with r.pubsub() as pubsub:
        await pubsub.psubscribe("wa_messages_channel")
        
        await asyncio.create_task(reader(pubsub))
