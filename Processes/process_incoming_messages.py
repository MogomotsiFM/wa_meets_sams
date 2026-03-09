import os
import re
import json
import asyncio
import logging
import mimetypes

import functools

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
        message = await channel.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is not None:
            json_msg = message["data"].decode()
            logger.info(f"(Reader) Message recieved: {json_msg}")
            if json_msg == STOPWORD:
                logger.info("(Reader) STOP")
                break
            await process_message(messanger, json_msg)
        logger.info("(Reader) Nothing to do...")
        await asyncio.sleep(1)


async def reader2(channel: redis.client.PubSub, process):
    #messanger = init()
    while True:
        message = await channel.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message is not None:
            json_msg = message["data"].decode()
            logger.info(f"(Reader) Message recieved: {json_msg}")
            if json_msg == STOPWORD:
                logger.info("(Reader) STOP")
                break
            await process(json_msg)
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


async def process_message_direct(r: redis.Redis, messanger: WhatsAppWrapper, message):
    try:
        logger.info("In here")
        json_msg = message["data"].decode()
        logger.info(f"(Reader) Message recieved: {json_msg}")

        body = json.loads(json_msg)
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
    except Exception as exp:
        logger.info(f"Error: {exp}")


@dataclass
class UploadedData:
    upload_id: str
    file_path: Path
    send_retries: int

    def __str__(self):
        path = str(self.file_path).replace("\\", "\\\\")
        return f'{{"upload_id":"{self.upload_id}", "file_path":"{path}", "send_retries":{self.send_retries}}}'


async def upload_data(r:redis.Redis, messanger: WhatsAppWrapper, message):
    try:
        logger.info("(UploadData) About to upload an artifact")
        file_path = message["data"].decode()
        logger.info(f"(Upload Data) Message recieved: {file_path}")

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
                logger.info(f"Publishing a message to {UPLOADED_ARTIFACTS}")
                msg = UploadedData(
                    upload_id = upload_response["id"],
                    file_path = file_path,
                    send_retries = 0
                )
                no = await r.publish(UPLOADED_ARTIFACTS, str(msg))
                logger.info(f"Published to {UPLOADED_ARTIFACTS}: {msg}, no. of subscribers: {no}")
                await asyncio.sleep(1)
            else:
                await r.publish(PENDING_DELIVERY_FILENAMES, str(file_path))
        else:
            error_msg = "Artifact has unknown content type"
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as exp:
        logger.error("(MessageProcessors) Failed to upload the school emblem.")
        logger.error(f"(MessageProcessors) Error: {exp}")
        # Put the file path back into the queue so we try uploading it again.
        await r.publish(PENDING_DELIVERY_FILENAMES, str(file_path))


async def send_opt_in_messages(r: redis.Redis, messanger: WhatsAppWrapper, message):#: UploadedData):
    logger.info("(Send Opt-In Messages) About to send an opt-in message")
    msg = message["data"].decode()
    logger.info(f"(Send Opt-In Messages) Message recieved: {msg}")
    # The first message should be the school emblem
    school_emblem_id = message.upload_id
    yield

    while True:
        await send_opt_in_messages_helper(r=r, messanger=messanger, message=msg, school_emblem_id=school_emblem_id)
        yield


async def send_opt_in_messages_helper(r: redis.Redis, messanger:WhatsAppWrapper, message: UploadedData, school_emblem_id: str):
    try:
        logger.info("About to send opt-in message")
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
            """
             Response from sending opt in message: {
             'messaging_product': 'whatsapp', 'contacts': [{'input': '27731948818', 'wa_id': '27731948818'}], 'messages': [{'id': 'wamid.HBgLMjc3MzE5NDg4MTgVAgARGBI3QTkwRjhBM0Q2MzJGRUI1NDEA', 'message_status': 'accepted'}]}
            """
            messages = response.setdefault("messages", [])
            if len(messages) > 0 and not messages[0].setdefault("id", None) is None:
                message = messages[0]
                r.set(message["id"], message.upload_id)
                break
        if (not response is None) and (response.setdefault("id", None) is None):
            message = UploadedData(
                upload_id = message.upload_id,
                file_path = message.file_path,
                send_retries = message.send_retries + 1
            )
            await r.publish(UPLOADED_ARTIFACTS, str(message))    
    except Exception as exp:
        logger.info(f"(MessageProccessor) Could send opt-in message to WhatsApp servers.")
        logger.info(f"(MessageProccessor)  Error: {exp}")
        message = UploadedData(
            upload_id = message.upload_id,
            file_path = message.file_path,
            send_retries = message.send_retries + 1
        )
        await r.publish(UPLOADED_ARTIFACTS, str(message))



async def send_opt_in_messages2(r: redis.Redis, messanger: WhatsAppWrapper):#: UploadedData):
    logger.info("Re mo teng")
    to_send = None
    message = yield to_send

    logger.info("(Send Opt-In Messages) About to send an opt-in message")
    msg = message["data"].decode()
    logger.info(f"(Send Opt-In Messages) Message recieved: {msg}")
    msg_json = json.loads(msg)
    # The first message should be the school emblem
    school_emblem_id = msg_json["upload_id"]

    while True:
        message = yield to_send
        msg = message["data"].decode()
        msg_json = UploadedData(**json.loads(msg))
        logger.info(f"(Send Opt-In Messages) Opt-in message destination: {msg_json}")
        await send_opt_in_messages_helper2(r=r, messanger=messanger, message=msg_json, school_emblem_id=school_emblem_id)


async def send_opt_in_messages_helper2(r: redis.Redis, messanger:WhatsAppWrapper, message: UploadedData, school_emblem_id: str):
    try:
        logger.info("About to send opt-in message")
        if message.send_retries > 3:
            logger.info(f"(MessageProcessor)  Message retried many times. It is possible that the phone number is not on WhatsApp.")
            # TODO: Add the message the dead letter queue
            return
        filepath = message.file_path
        matches: list[str] = re.findall("(?<=Tel)[ \d]{10,}", str(filepath))
        response = None
        for phone_number in matches:
            phone_number = phone_number.strip()
            if phone_number[0] == '0':
                phone_number = re.sub("0", "27", phone_number)
            logger.info(f"(MessageProcessor)  Extracted phone number: {phone_number}")
            response = await messanger.send_opt_in_message(phone_number, school_emblem_id, date="March 6", weekday="Friday", time="10.30am")
            logger.debug(f"(Reader)  Response from sending opt in message: {response}")
            """
             Response from sending opt in message: {
             'messaging_product': 'whatsapp', 'contacts': [{'input': '27731948818', 'wa_id': '27731948818'}], 'messages': [{'id': 'wamid.HBgLMjc3MzE5NDg4MTgVAgARGBI3QTkwRjhBM0Q2MzJGRUI1NDEA', 'message_status': 'accepted'}]}
            """
            messages = response.setdefault("messages", [])
            if len(messages) > 0 and not messages[0].setdefault("id", None) is None:
                response_msg = messages[0]
                await r.set(response_msg["id"], message.upload_id)
                return

        message = UploadedData(
            upload_id = message.upload_id,
            file_path = message.file_path,
            send_retries = message.send_retries + 1
        )
        await r.publish(UPLOADED_ARTIFACTS, str(message))    
    except Exception as exp:
        logger.info(f"(MessageProccessor) Could not send opt-in message to WhatsApp servers.")
        logger.info(f"(MessageProccessor)  Error: {exp}")
        message = UploadedData(
            upload_id = message.upload_id,
            file_path = message.file_path,
            send_retries = message.send_retries + 1
        )
        await r.publish(UPLOADED_ARTIFACTS, str(message))


async def handle_opt_in_responses(r: redis.Redis, message, messanger: WhatsAppWrapper):
    logger.debug("(Handle Opt-In Response) About to upload a progress report.")
    try:
        raw_msg = message["data"].decode()
        logger.info(f"(Handle Opt-In Response) Message recieved: {raw_msg}")

        body = json.loads(raw_msg)
        entries = body["entry"]
        entry = entries[0]
        changes = entry["changes"]
        change = changes[0]
        value: dict = change["value"]
        msgs = value.setdefault("messages", [])

        if len(msgs) > 0:
            msg = msgs[0]
            context = msg["context"]
            opt_in_id = context["id"]
            report_id = await r.get(opt_in_id)
            btn = msg["button"]
            if btn["text"] == "Accept":
                logger.info(f"Source phone number: {msg['from']}, report_id: {report_id}({type(report_id)})")
                response = await messanger.send_progress_report(str(msg["from"]), str(report_id))
                logger.debug(f"(MessageProcessor)  Response from sending a progress report message: {response}")

                error_code = response.setdefault("status_code", 200)
                if error_code < 300:
                    logger.info("The progress report was successfully sent to WA.")
                elif error_code < 500: # Client error, we can only adjust our request parameters.
                    error_msg = f'Client error: {response["message"]}'
                    logger.info(error_msg)
                    raise ValueError(error_msg)
                else: # Server error
                    logger.error(f'Server error: {response["message"]}')
                    # TODO: Backoff using aiohttp library??
                    await r.set(opt_in_id, report_id)
                    await asyncio.sleep(15)
                    await r.publish(OPT_IN_RESPONSES, raw_msg)
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


def signature_preserving_decorator(processor, messanger: WhatsAppWrapper, r: redis.Redis):
    @functools.wraps(processor)
    async def wrapper(message):
        return await processor(r=r, messanger=messanger, message=message)
    return wrapper


def signature_preserving_decorator2(processor, messanger: WhatsAppWrapper, r: redis.Redis):
    @functools.wraps(processor)
    async def wrapper(message):
        return processor(r=r, messanger=messanger, message=message)
    return wrapper


async def process_messages():
    r = await redis.from_url("redis://localhost")#, decode_responses=True)
    messanger = init()

    async with r.pubsub() as pubsub:
        try:
            #process = lambda msg: process_message_direct(messanger=messanger, message=msg)
            process = signature_preserving_decorator(process_message_direct, messanger, r)
            await pubsub.subscribe(**{OPT_IN_RESPONSES: process})
            await asyncio.create_task(pubsub.run())
        except Exception as exp:
            logger.info(f"Error: {exp}")


async def process_messages_():
    r = await redis.from_url("redis://localhost")
    messanger = init()

    async with r.pubsub() as pubsub:
        #pending = lambda msg: upload_data(r=r, messanger=messanger, file_path=msg)
        pending = signature_preserving_decorator(upload_data, messanger, r)
        #uploaded = lambda msg: send_opt_in_messages(r=r, messanger=messanger, message=msg)
        #uploaded = signature_preserving_decorator(send_opt_in_messages, messanger, r)
        uploaded = send_opt_in_messages2(r=r, messanger=messanger)
        await uploaded.asend(None)
        #opt_in = lambda msg: handle_opt_in_responses(r=r, messanger=messanger, msg=msg)
        opt_in = signature_preserving_decorator(handle_opt_in_responses, messanger, r)
        #await pubsub.subscribe(
        #    UPLOADED_ARTIFACTS,
        #    **{
        #        PENDING_DELIVERY_FILENAMES: pending,
        #        #UPLOADED_ARTIFACTS: uploaded,
        #        OPT_IN_RESPONSES: opt_in
        #    }
        #)
        #await asyncio.create_task(pubsub.run())
        await pubsub.subscribe(UPLOADED_ARTIFACTS, PENDING_DELIVERY_FILENAMES, OPT_IN_RESPONSES)
        async for message in pubsub.listen():
            if message['type'] == 'message':
                logger.info(f"Message: {message}")
                channel = message["channel"].decode()
                if channel == UPLOADED_ARTIFACTS:
                    logger.info("In there")
                    #asyncio.create_task(uploaded(message))
                    #await uploaded.asend(message)
                    asyncio.create_task(uploaded.asend(message))
                elif channel == PENDING_DELIVERY_FILENAMES:
                    logger.info("In here")
                    await pending(message)
                elif channel == OPT_IN_RESPONSES:
                    await opt_in(message)



