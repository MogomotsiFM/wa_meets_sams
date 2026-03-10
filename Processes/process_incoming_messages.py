import os
import re
import json
import asyncio
import logging
import mimetypes

import functools

import dataclasses
from typing import Literal, List

import redis.asyncio as redis
import redis.client as client

from pathlib import Path

from Messangers.wa_wrapper import WhatsAppWrapper

from dotenv import load_dotenv
load_dotenv()

STOPWORD = "STOP"

# TODO: How to handle parents with multiple children. We do not need to send 
#       multiple opt-in messages to the same number.
# TODO: If a guardian opts to fetch the report from school then we need to add 
#       that report to the dead letter queue. This means that we have to decrypt 
#       that report.
# TODO: It is also possible that a phone number is not on WhatsApp. Again, we must 
#       add the corresponding report to the dead letter queue.
# TODO: Join all the reports in the dead letter queue for easy printing. We may 
#       also want to remove the report cover pages.
# TODO: Generate some sort of report at the end. How many reports were sent via
#       WA? How many per grade? How many still need to be collected?

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


@dataclasses.dataclass
class UploadedData:
    upload_id: str
    file_path: Path
    send_retries: int

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)


async def upload_data(r:redis.Redis, messanger: WhatsAppWrapper, message):
    try:
        logger.info("(UploadData) About to upload an artifact")
        file_path = message["data"].decode()
        logger.info(f"(Upload Data) Message recieved: {file_path}")

        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is not None:
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


@dataclasses.dataclass
class OptInStatus:
    status: Literal["Unknown", "Accept", "Decline"]
    #phone_number: str
    opt_in_msg_id: str
    # It is possible that a parent has multiple kids at a school
    # This keeps the list of reports associated with that parent's phone number
    reports: List[Path]

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)


    @staticmethod
    def create(data: str):
        j = json.loads(data)
        return OptInStatus(**j)

    @staticmethod
    def simulate_parent_decision(decision: Literal["Accept", "Decline"]):
        msg = 


async def send_opt_in_messages(r: redis.Redis, messanger: WhatsAppWrapper):
    logger.info("Re mo teng")
    to_send = None
    # This is part of sending data into a generator.
    # The other half is calling the send method of the generator with the data.
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
        await send_opt_in_messages_helper(r=r, messanger=messanger, message=msg_json, school_emblem_id=school_emblem_id)


async def send_opt_in_messages_helper(r: redis.Redis, messanger:WhatsAppWrapper, message: UploadedData, school_emblem_id: str):
    try:
        logger.info("About to send opt-in message")
        if message.send_retries > 3:
            logger.info(f"(MessageProcessor)  Message retried many times. It is possible that the phone number is not on WhatsApp.")
            # TODO: Add the message to the dead letter queue
            return
        filepath = message.file_path
        matches: list[str] = re.findall("(?<=Tel)[ \d]{10,}", str(filepath))
        response = None
        for phone_number in matches:
            phone_number = phone_number.strip()
            if phone_number[0] == '0':
                phone_number = re.sub("0", "27", phone_number)
            logger.info(f"(MessageProcessor)  Extracted phone number: {phone_number}")

            # Check the phone number in the status KV store
            data = await r.get(phone_number)
            if data is None:
                response = await messanger.send_opt_in_message(phone_number, school_emblem_id, date="March 6", weekday="Friday", time="10.30am")
                logger.debug(f"(MessageProcessors)  Response from sending opt in message: {response}")
            
                messages = response.setdefault("messages", [])
                if len(messages) > 0 and not messages[0].setdefault("id", None) is None:
                    response_msg = messages[0]
                    await r.set(response_msg["id"], message.upload_id)

                    opt_in_status = OptInStatus("Unknown", response_msg["id"], [message.file_path])
                    await r.set(phone_number, str(opt_in_status))
                    return
            else:
                logger.info("An opt-in message has already been sent to this number because it is associated with at least two reports")
                opt_in_status = OptInStatus.create(data.decode())
                key = f"opt_in_status.opt_in_msg_id_{len(opt_in_status.reports)}" 
                # Add the progress report to the KV store of report that need to be sent.
                await r.set(key, message.upload_id)

                # Simulate the parent accepting/declining the offer to opt-in request.



        # At this point we failed to send the opt-in message for whatever reason
        # So, we insert the message so we have another chance at processing it.
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
            report_id = report_id.decode('utf-8')
            btn = msg["button"]
            if btn["text"] == "Accept":
                logger.info(f"Source phone number: {msg['from']}, report_id: {report_id}({type(report_id)})")
                response = await messanger.send_progress_report(str(msg["from"]), str(report_id))
                logger.debug(f"(MessageProcessor)  Response from sending a progress report message: {response}")

                error_code = response.setdefault("status_code", 403)
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


def signature_preserving_decorator(processor, messanger: WhatsAppWrapper, r: redis.Redis):
    @functools.wraps(processor)
    async def wrapper(message):
        return await processor(r=r, messanger=messanger, message=message)
    return wrapper


async def process_messages():
    r = await redis.from_url("redis://localhost")
    messanger = init()

    async with r.pubsub() as pubsub:
        pending = signature_preserving_decorator(upload_data, messanger, r)
        uploaded = send_opt_in_messages(r=r, messanger=messanger)
        # The first message pushed into a generator has to be None.
        await uploaded.asend(None)
        opt_in = signature_preserving_decorator(handle_opt_in_responses, messanger, r)

        await pubsub.subscribe(UPLOADED_ARTIFACTS, PENDING_DELIVERY_FILENAMES, OPT_IN_RESPONSES)

        async for message in pubsub.listen():
            if message['type'] == 'message':
                logger.info(f"Message: {message}")
                channel = message["channel"].decode()
                if channel == UPLOADED_ARTIFACTS:
                    asyncio.create_task(uploaded.asend(message))
                elif channel == PENDING_DELIVERY_FILENAMES:
                    await pending(message)
                elif channel == OPT_IN_RESPONSES:
                    await opt_in(message)



