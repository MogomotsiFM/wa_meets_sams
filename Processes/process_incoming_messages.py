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

logging.getLogger().setLevel(logging.DEBUG)
logger = logging.getLogger()

OptInDecision = Literal["Unknown", "Accept", "Decline"]

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

    @staticmethod
    def create(data: str):
        j = json.loads(data)
        return UploadedData(**j)


async def upload_data(r: redis.Redis, kv: redis.Redis, messanger: WhatsAppWrapper, message):
    """
    r: Used for pub-sub
    kv: Used as a key-value store
    """
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
            error_msg = f"Artifact has unknown content type: {file_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as exp:
        logger.error("(MessageProcessors) Failed to upload the school emblem.")
        logger.error(f"(MessageProcessors) Error: {exp}")
        # Put the file path back into the queue so we try uploading it again.
        await r.publish(PENDING_DELIVERY_FILENAMES, str(file_path))


@dataclasses.dataclass
class OptInStatus:
    status: OptInDecision
    #phone_number: str
    opt_in_msg_id: str
    # It is possible that a parent has multiple kids at a school
    # This keeps the list of reports associated with that parent's phone number
    reports: List[Path]
    reports_status: List[Literal["sent", "not-sent"]]

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)


    @staticmethod
    def create(data: str):
        j = json.loads(data)
        obj = OptInStatus(**j)
        return obj


    @staticmethod
    def emulate_decision(parent_tel: str, opt_in_msg_id: str, decision: OptInDecision):
        """
        src_msg_id: Will be used to lookup the report upload id so that it may be send to the parent
        """
        msg = [
            {
                "context":{
                    "from":"not_applicable",
                    "id":opt_in_msg_id
                },
                "from":parent_tel,
                "id":"not_applicable",
                "timestamp":"not_applicable",
                "type":"button",
                "button":{
                    "payload":str(decision),
                    "text":str(decision)
                }
            }
        ]
        return msg


async def send_opt_in_messages(r: redis.Redis, kv: redis.Redis, messanger: WhatsAppWrapper):
    """
    r: Used for pub-sub
    kv: Used as a key-value store
    """
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
        msg_str = message["data"].decode()
        msg = UploadedData(**json.loads(msg_str))
        logger.info(f"(Send Opt-In Messages) Opt-in message destination: {msg}")
        await send_opt_in_messages_helper(r=r, kv=kv, messanger=messanger, message=msg, school_emblem_id=school_emblem_id)


async def send_opt_in_messages_helper(r: redis.Redis, kv: redis.Redis, messanger:WhatsAppWrapper, message: UploadedData, school_emblem_id: str):
    """
    r: Used for pub-sub
    kv: Used as a key-value store
    """
    try:
        logger.info("About to send opt-in message")
        if message.send_retries > 3:
            logger.info(f"(MessageProcessor)  Message retried many times. It is possible that the phone number is not on WhatsApp.")
            # TODO: Add the message to the dead letter queue
            return
        filepath = message.file_path
        matches: list[str] = re.findall("(?<=Tel)[ \d]{10,}", str(filepath))
        for phone_number in matches:
            phone_number = phone_number.strip()
            if phone_number[0] == '0':
                phone_number = re.sub("0", "27", phone_number)
            logger.info(f"(MessageProcessor)  Extracted phone number: {phone_number}")

            # Check the phone number in the status KV store
            data = await kv.get(phone_number)
            logger.debug(f"\nData: {data}\n")
            if data == None:
                logger.debug(f"Sending an opt-in message for the first time: {phone_number}")
                response = await messanger.send_opt_in_message(phone_number, school_emblem_id, date="March 6", weekday="Friday", time="10.30am")
                logger.debug(f"(MessageProcessors)  Response from sending opt in message: {response}")
            
                messages = response.setdefault("messages", [])
                if len(messages) > 0 and not messages[0].setdefault("id", None) is None:
                    response_msg = messages[0]
                    await kv.set(response_msg["id"], str(message))

                    ois = OptInStatus("Unknown", response_msg["id"], [message.file_path], ["not-sent"])
                    await kv.set(phone_number, str(ois))
                    return
            else:
                # What is the chance the application crashed, was restarted, and we have seen the filename before?
                ois = OptInStatus.create(data.decode())
                try:
                    idx = ois.reports.index(message.file_path)
                    logger.info(f"(MessageProcessors) The report at index {idx} has already been processed.")
                    logger.debug(f"(MessageProcessor) Filename: {message.file_path}")
                    return
                except Exception as exp:
                    logger.info(f"(MessageProcessor) {exp}")
                    logger.info("An opt-in message has already been sent to this number because it is associated with at least two reports")
                    # ois = opt_in_status
                    
                    if not ois.status == "Unknown":
                        logger.debug(f"Opt-in status: {ois.status}")
                        key = f"{ois.opt_in_msg_id}_{len(ois.reports)}" 
                        # Add the progress report to the KV store of report that need to be sent.
                        await kv.set(key, str(message))

                        ois.reports.append(message.file_path)
                        ois.reports_status.append("not-sent")
                        new_opt_in_status = OptInStatus(ois.status, ois.opt_in_msg_id, ois.reports, ois.reports_status)
                        await kv.set(phone_number, str(new_opt_in_status))

                        # Emulate the parent accepting/declining the offer to opt-in request.
                        msg = OptInStatus.emulate_decision(phone_number, key, ois.status)
                        await r.publish(OPT_IN_RESPONSES, json.dumps(msg))

                        return
                    else:
                        logger.debug("Parent has not responded to the opt-in message that we sent.")
                        await asyncio.sleep(5)
                        await r.publish(UPLOADED_ARTIFACTS, str(message))

                        return

        await asyncio.sleep(10)
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


async def handle_opt_in_responses(r: redis.Redis, kv: redis.Redis, message, messanger: WhatsAppWrapper):
    """
        r: Used for pub-sub
        kv: Used as a key-value store
    """
    logger.debug("(Handle Opt-In Response) About to upload a progress report.")
    raw_msg = message["data"].decode()
    logger.info(f"(Handle Opt-In Response) Message recieved: {raw_msg}")
    try:
        msgs = json.loads(raw_msg)
        msg = msgs[0]
        context = msg["context"]
        opt_in_id = context["id"]
        uploaded_data = await kv.get(opt_in_id)
        uploaded_data = UploadedData.create(uploaded_data.decode())
        report_id = uploaded_data.upload_id
        btn = msg.setdefault("button", None)
        if btn is not None:
            data = await kv.get(msg["from"])
            # opt_in_info = oii
            oii = OptInStatus.create(data.decode())
            oii.status = btn["text"]
            await kv.set(msg["from"], str(oii))

            # Any chance that the application crashed, was restarted, and some of the messages had already been sent?'
            # list::index raises an exception if a value is not found. We should always find what we are looking for.
            idx = oii.reports.index(uploaded_data.file_path)
            if not oii.reports_status[idx] == "sent":
                if btn["text"] == "Accept":
                    logger.info(f"Source phone number: {msg['from']}, report_id: {report_id}({type(report_id)})")
                    response = await messanger.send_progress_report(str(msg["from"]), str(report_id))
                    logger.debug(f"(MessageProcessor)  Response from sending a progress report message: {response}")

                    status = response["messages"][0]["message_status"]
                    logger.info(f"(MessageProcessor) Opt in status: {status}")
                    if status == "accepted":
                        oii.reports_status[idx] = "sent"
                        await kv.set(msg["from"], str(oii))

                        logger.info("The progress report was successfully sent to WA.")
                    else: # Server error
                        logger.error(f'Server error: {response["message"]}')
                        # TODO: Backoff using aiohttp library??
                        await kv.set(opt_in_id, str(uploaded_data))
                        await asyncio.sleep(15)
                        await r.publish(OPT_IN_RESPONSES, raw_msg)
                elif btn["text"] == "Decline":
                    # We add them to the list of parents for whom we must print progress reports.
                    # We could also send a reminder a day before the day of collection.
                    logger.debug(f"(MessageProcessor)  The parent chose to come to school to collect the report.")
                    logger.debug("(MessageProcessor)  Add the message to dead letter queue. Decrypt if first.")
                else:
                    raise ValueError("Incorrect message format. Expected a button field and none was found.")
    except Exception as exp:
        logger.info(f"(MessageProcessor) Error: {exp}")
        await asyncio.sleep(15)
        await r.publish(OPT_IN_RESPONSES, raw_msg)


def signature_preserving_decorator(processor, messanger: WhatsAppWrapper, r: redis.Redis, kv: redis.Redis):
    @functools.wraps(processor)
    async def wrapper(message):
        return await processor(r=r, kv=kv, messanger=messanger, message=message)
    return wrapper


async def process_messages():
    r  = await redis.from_url("redis://localhost", db=0)
    kv = await redis.from_url("redis://localhost", db=1)
    
    messanger = init()

    async with r.pubsub() as pubsub:
        pending = signature_preserving_decorator(upload_data, messanger, r, kv)
        uploaded = send_opt_in_messages(r=r, kv=kv, messanger=messanger)
        # The first message pushed into a generator has to be None.
        await uploaded.asend(None)
        opt_in = signature_preserving_decorator(handle_opt_in_responses, messanger, r, kv)

        await pubsub.subscribe(UPLOADED_ARTIFACTS, PENDING_DELIVERY_FILENAMES, OPT_IN_RESPONSES)

        async for message in pubsub.listen():
            if message['type'] == 'message':
                logger.info(f"Message: {message}")
                channel = message["channel"].decode()
                if channel == UPLOADED_ARTIFACTS:
                    #try:
                    await asyncio.create_task(uploaded.asend(message))
                    #except Exception as exp:
                    #    logger.info(exp)
                    #    await asyncio.sleep(1.0)
                    #    await r.publish(UPLOADED_ARTIFACTS, message["data"].decode())
                elif channel == PENDING_DELIVERY_FILENAMES:
                    await pending(message)
                elif channel == OPT_IN_RESPONSES:
                    await opt_in(message)



