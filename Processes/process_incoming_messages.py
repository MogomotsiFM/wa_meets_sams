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
        message = await channel.get_message(ignore_subscribe_messages=True, timeout=1)
        if message is not None:
            json_msg = message["data"].decode()
            logger.info(f"(Reader) Message recieved: {json_msg}")
            if json_msg == STOPWORD:
                logger.info("(Reader) STOP")
                break
            await process_message(messanger, json_msg)
        logger.info("(Reader) Nothing to do...")
        await asyncio.sleep(1)


async def process_message(messanger: WhatsAppWrapper, body_bytes: bytes):
    body = json.loads(body_bytes)
    entries = body["entry"]
    entry = entries[0]
    changes = entry["changes"]
    change = changes[0]
    value: dict = change["value"]
    msgs = value.setdefault("messages", [])
    for msg in msgs:
        if msg["type"] == "text":
            await handle_text_message(msg, messanger)
        elif msg["type"] == "button":
            await handle_button_message(msg, messanger)
        else:
            logger.info(f"(Message Processor) Message type {msg['type']} has not been implemented.")


async def handle_button_message(msg: dict, messanger: WhatsAppWrapper):
    logger.debug("(Reader) About to upload a progress report.")
    try:
        file_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\Mogomotsi KEAIKITSE - Tel0710491875 - EMailamg.seiphemo@gmail.com.pdf"
        upload_re = await messanger.upload(file_path, "Progress Report")
        logger.info(f"(Reader)  Upload progress report response: {upload_re}")
        await asyncio.sleep(1)
        btn = msg["button"]
        if btn["text"] == "Accept":
            response = await messanger.send_progress_report(msg["from"], upload_re["id"])
            logger.debug(f"(Reader)  Response from sending a progress report message: {response}")
        else:
            # We add them to the list of parents for whom we must print progress reports.
            # We could also send a reminder a day before the day of collection.
            logger.debug(f"(WhatsappWrapper)  The parent chose to come to school to collect the report.")
    except Exception:
        logger.info(f"(WhatsappWrapper) Could not upload {file_path} to WhatsApp server.")


async def handle_text_message(msg: dict, messanger: WhatsAppWrapper):
    logger.info(f"(WhatsappWrapper)  Received message: {msg['text']}")

    try:
        img_path = r"C:\Users\GAME\Desktop\Projects\whatsapp_sams\Data\school_emblem.png"
        upload_re = await messanger.upload(img_path, "school_emblem")
        logger.info(f"(Reader)  Upload school emblem response: {upload_re}")
        await asyncio.sleep(1)
        response = await messanger.send_opt_in_message(msg["from"], upload_re["id"], date="March 6", weekday="Friday", time="10.30am")
        logger.debug(f"(Reader)  Response from sending opt in message: {response}")
    except Exception:
        logger.info(f"(WhatsappWrapper) Could not upload {img_path} to WhatsApp server.")


async def process_messages():
    r = await redis.from_url("redis://localhost")
    async with r.pubsub() as pubsub:
        await pubsub.psubscribe("wa_messages_channel")
        
        await asyncio.create_task(reader(pubsub))
