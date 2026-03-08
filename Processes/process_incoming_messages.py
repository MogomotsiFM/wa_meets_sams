import os
import re
import json
import asyncio
import logging
import mimetypes

from pydantic.dataclasses import dataclass
from typing import Callable

import redis.asyncio as redis
import redis.client as client

from pathlib import Path

from Messangers.wa_wrapper import WhatsAppWrapper

from dotenv import load_dotenv
load_dotenv()

STOPWORD = "STOP"

logger = logging.getLogger()

PENDING_DELIVERY_FILENAMES = os.getenv("PENDING_DELIVERY_FILENAMES")
UPLOADED_ARTIFACTS = os.getenv("UPLOADED_ARTIFACTS")
OPT_IN_RESPONSES = os.getenv("OPT_IN_RESPONSES")
if PENDING_DELIVERY_FILENAMES is None or UPLOADED_ARTIFACTS is None or OPT_IN_RESPONSES is None:
    raise ValueError("All the three redis channel names should be define in environment variable.")


def init() -> WhatsAppWrapper:
    WA_SAMS_TOKEN = os.getenv("WA_SAMS_TOKEN")
    WA_SAMS_PHONE_ID = os.getenv("WA_SAMS_PHONE_ID")
    if WA_SAMS_TOKEN is None or WA_SAMS_PHONE_ID is None:
        raise ValueError("WA_SAMS_TOKEN and WA_SAMS_PHONE_ID environment variables should be set.")
    
    messanger = WhatsAppWrapper(bearer_token=WA_SAMS_TOKEN, phone_number_id=WA_SAMS_PHONE_ID)
    logger.debug(f"(MessageProcessors)  token: {WA_SAMS_TOKEN}")
    logger.debug(f"(MessageProcessors)  Phone Id: {WA_SAMS_PHONE_ID}")

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


async def reader_(channel: client.PubSub, messanger: WhatsAppWrapper, process_message):#: Callable[[WhatsAppWrapper, bytes], None]):
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
            logger.info(f"(MessageProcessors) Message type {msg['type']} has not been implemented.")


@dataclass
class UploadedData:
    upload_id: str
    file_path: Path
    send_retries: int

    def __str__(self):
        return f"{{upload_id: {self.upload_data}, file_path: {self.file_path}, send_retries: {self.send_retries}}}"



async def upload_data(r:redis.Redis, messanger: WhatsAppWrapper, file_path: Path):
    #r = await redis.from_url("redis://localhost")

    try:
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type is None:
            if "image" in content_type:
                logger.info("(MessageProcessors) Uploading the school emblem.")
                upload_response = await messanger.upload(file_path, "school_emblem")
                logger.info(f"(MessageProcessors) Upload emblem response: {upload_response}")
            else:
                logger.info(f"(MessageProcessors) Uploading progress report: {file_path}")
                upload_response = await messanger.upload(file_path, "school_report")
                logger.info(f"(MessageProcessors) Upload report response: {upload_response}")

            if upload_response.setdefault("id", None) is not None:
                msg = UploadedData(
                    upload_id = upload_response["id"],
                    file_path = file_path,
                    send_retries = 0
                )
                r.publish(UPLOADED_ARTIFACTS, str(msg))
                await asyncio.sleep(1)
            else:
                r.publish(PENDING_DELIVERY_FILENAMES, str(file_path))
            
    except Exception as exp:
        logger.info("(MessageProcessors) Failed to upload the school emblem.")
        logger.info(f"(MessageProcessors) Error: {exp}")
        # Put the file path back into the queue so we try uploading it again.
        r.publish(PENDING_DELIVERY_FILENAMES, str(file_path))


async def send_opt_in_messages(r: redis.Redis, messanger:WhatsAppWrapper, message: UploadedData, school_emblem_id:str):
    #r = await redis.from_url("redis://localhost")
    try:
        filepath = message.file_path
        if message.send_retries > 3:
            logger.info(f"(MessageProcessor)  Message retried many times. It is possible that the phone number is not on WhatsApp.")
            # Add the message the dead letter queue
        matches: list[str] = re.findall("(?<=Tel)[ \d]{10,}", str(filepath))
        response = None
        for phone_number in matches:
            phone_number = phone_number.strip()
            if phone_number[0] == '0':
                tel = re.sub("0", "27", phone_number)
            logger.info("f(MessageProcessor)  Extracted phone number: {tel}")
            response = await messanger.send_opt_in_message(tel, school_emblem_id, date="March 6", weekday="Friday", time="10.30am")
            logger.debug(f"(Reader)  Response from sending opt in message: {response}")
            if not response.setdefault("id", None) is None:
                r.set(response["id"], message.upload_id)
                break
        if (not response is None) and (response.setdefault("id", None) is None):
            message = UploadedData(
                upload_id = message.upload_id,
                file_path = message.file_path,
                send_retries = message.send_retries + 1
            )
            r.publish(UPLOADED_ARTIFACTS, str(message))    
    except Exception as exp:
        logger.info(f"(MessageProccessor) Could send opt-in message to WhatsApp servers.")
        logger.info(f"(MessageProccessor)  Error: {exp}")
        message = UploadedData(
            upload_id = message.upload_id,
            file_path = message.file_path,
            send_retries = message.send_retries + 1
        )
        r.publish(UPLOADED_ARTIFACTS, str(message))


async def handle_button_message_(r: redis.Redis, msg: dict, messanger: WhatsAppWrapper):
    logger.debug("(Reader) About to upload a progress report.")
    try:
        context = msg["context"]
        opt_in_id = context["id"]
        report_id = r.get(opt_in_id)
        btn = msg["button"]
        if btn["text"] == "Accept":
            response = await messanger.send_progress_report(msg["from"], report_id)
            logger.debug(f"(MessageProcessor)  Response from sending a progress report message: {response}")
        else:
            # We add them to the list of parents for whom we must print progress reports.
            # We could also send a reminder a day before the day of collection.
            logger.debug(f"(MessageProcessor)  The parent chose to come to school to collect the report.")
            logger.debug("(MessageProcessor)  Add the message to dead letter queue. Decrypt if first.")
    except Exception as exp:
        logger.info(f"(MessageProcessor) Error: {exp}")


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
    #pubsub = r.pubsub()
    #await pubsub.psubcribe("wa_messages_channel")
    #await asyncio.create_task(reader(pubsub))
    async with r.pubsub() as pubsub:
        await pubsub.psubscribe("wa_messages_channel")
        
        await asyncio.create_task(reader(pubsub))
        

async def process_messages_():
    r = await redis.from_url("redis://localhost")
    #pubsub = r.pubsub()
    #await pubsub.psubcribe("wa_messages_channel")
    #await asyncio.create_task(reader(pubsub))
    async with r.pubsub() as pending_delivery_channel:
        async with r.pubsub() as uploaded_artifacts_channel:
            async with r.pubsub as opt_in_responses_channel:
                await pending_delivery_channel.psubscribe(PENDING_DELIVERY_FILENAMES)
                await asyncio.create_task(reader(pending_delivery_channel))

                await uploaded_artifacts_channel.psubscribe(UPLOADED_ARTIFACTS)
                await asyncio.create_tast(reader(uploaded_artifacts_channel))

                await opt_in_responses_channel.psubscribe(OPT_IN_RESPONSES)
                await asyncio.create_task(reader(opt_in_responses_channel))


