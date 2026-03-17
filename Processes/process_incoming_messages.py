import os
import re
import json
import asyncio
import logging
import mimetypes

import functools

import dataclasses
from typing import Literal, List

from pathlib import Path

import redis.asyncio as redis
import redis.client as client

from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from Messangers.wa_wrapper import WhatsAppWrapper

from .comms_data_structs import UploadedData, ReportDeliveryInfo

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

scheduler = AsyncIOScheduler()

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")
REDIS_KV_STORE_DB = os.getenv("KV_STORE_DB")

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


async def async_publish(r: redis.Redis, channel, message: str):
    await r.publish(channel, message)


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
                ct = datetime.now()
                logger.debug(f"(MessageProcessors) Current time: {ct}")
                run_date = ct + timedelta(seconds=30)
                scheduler.add_job(func=async_publish, args=[r, PENDING_DELIVERY_FILENAMES, str(file_path)], trigger="date", run_date=run_date)
        else:
            error_msg = f"Artifact has unknown content type: {file_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as exp:
        logger.error("(MessageProcessors) Failed to upload the school emblem.")
        logger.error(f"(MessageProcessors) Error: {exp}")
        # Put the file path back into the queue so we try uploading it again.
        ct = datetime.now()
        logger.debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(seconds=30)
        scheduler.add_job(func=async_publish, args=[r, PENDING_DELIVERY_FILENAMES, str(file_path)], trigger="date", run_date=run_date)


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
        msg = UploadedData.create(msg_str)
        logger.info(f"(Send Opt-In Messages) Opt-in message destination: {msg}")
        await send_opt_in_messages_helper(r=r, kv=kv, messanger=messanger, message=msg, school_emblem_id=school_emblem_id)


async def send_opt_in_messages_helper(r: redis.Redis, kv: redis.Redis, messanger:WhatsAppWrapper, message: UploadedData, school_emblem_id: str):
    """
    r: Used for pub-sub
    kv: Used as a key-value store
    """
    try:
        # We have not found a number that is on WA
        wa_number_found = False

        logger.info("About to send opt-in message")
        if message.send_retries <= 5:
            filepath = message.file_path
            matches: list[str] = re.findall("(?<=Tel)[ \d]{10,}", str(filepath))
            for phone_number in matches:
                phone_number = phone_number.strip()
                if phone_number[0] == '0':
                    phone_number = re.sub("0", "27", phone_number, 1)
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

                        rdi = ReportDeliveryInfo("Unknown", response_msg["id"], [message.file_path], ["not-sent"])
                        await kv.set(phone_number, str(rdi))
                        
                        # We found a number registered on WA
                        wa_number_found = True
                        break
                    else:
                        logger.info(f"(MessageProcessor) Failed to send the opt-in message to {phone_number}. Trying another number.")
                        await asyncio.sleep(1)
                else:
                    # What is the chance the application crashed, was restarted, and we have seen the filename before?
                    rdi = ReportDeliveryInfo.create(data.decode())
                    try:
                        ids = [i for i, fp in enumerate(rdi.reports) if Path(message.file_path).name in fp]
                        idx = ids[0]
                        #idx = rds.reports.index(message.file_path)
                        logger.info(f"(MessageProcessors) The report at index {idx} has already been processed.")
                        logger.debug(f"(MessageProcessor) Filename: {message.file_path}")
                    except Exception as exp:
                        logger.info(f"(MessageProcessor) {exp}")
                        logger.info("An opt-in message has already been sent to this number because it is associated with at least two reports")
                        # ois = opt_in_status
                        
                        if not rdi.opt_in_status == "Unknown":
                            logger.debug(f"Opt-in status: {rdi.opt_in_status}")
                            key = f"{rdi.opt_in_msg_id}_{len(rdi.reports)}" 
                            # Add the progress report to the KV store of report that need to be sent.
                            await kv.set(key, str(message))

                            new_rds = rdi.add_report(message.file_path, "not-sent")
                            await kv.set(phone_number, str(new_rds))

                            # Emulate the parent accepting/declining the offer to the opt-in request.
                            msg = ReportDeliveryInfo.emulate_decision(phone_number, key, rdi.opt_in_status)
                            await r.publish(OPT_IN_RESPONSES, json.dumps(msg))
                            #await r.xadd(OPT_IN_RESPONSES, json.dumps(msg))
                        else:
                            logger.info("Parent has not responded to the opt-in message that we sent.")
                            logger.debug("Resubmiting the report so it may be processed later.")
                            ct = datetime.now()
                            logger.debug(f"(MessageProcessors) Current time: {ct}")
                            run_date = ct + timedelta(seconds=30)
                            scheduler.add_job(func=async_publish, args=[r, UPLOADED_ARTIFACTS, str(message)], trigger="date", run_date=run_date)

                    # We are in this else statement because we have been able to send an opt-in message to this number.
                    # So, we know it works and there is no need to try another number.
                    wa_number_found = True
                    break
            # Did we find a number that is on WA?
            if not wa_number_found:
                logger.info("(MessageProcessor) We could not send a message to any of the listed phone numbers. We will retry later.")
                message.send_retries = message.send_retries + 1
                ct = datetime.now()
                logger.debug(f"(MessageProcessors) Current time: {ct}")
                run_date = ct + timedelta(seconds=30)
                scheduler.add_job(func=async_publish, args=[r, UPLOADED_ARTIFACTS, str(message)], trigger="date", run_date=run_date)
        else:
            # TODO: Add the message to the dead letter queue
            logger.info(f"(MessageProcessor)  Message retried many times. It is possible that the phone number is not on WhatsApp.")

    except Exception as exp:
        logger.info(f"(MessageProccessor) Could not send opt-in message to WhatsApp servers.")
        logger.info(f"(MessageProccessor)  Error: {exp}")
        message.send_retries = message.send_retries + 1
        ct = datetime.now()
        logger.debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(seconds=30)
        scheduler.add_job(func=async_publish, args=[r, UPLOADED_ARTIFACTS, str(message)], trigger="date", run_date=run_date)


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
        context = msg.setdefault("context", None)
        if context is not None and context.setdefault("id", None) is not None:
            opt_in_id = context["id"]
            uploaded_data = await kv.get(opt_in_id)
            # uploaded_data = await kv.xread(opt_in_id)
            uploaded_data = UploadedData.create(uploaded_data.decode())
            report_id = uploaded_data.upload_id
            btn = msg.setdefault("button", None)
            if btn is not None:
                data = await kv.get(msg["from"])
                # report_delivery_status = rds
                rdi = ReportDeliveryInfo.create(data.decode())
                rdi.opt_in_status = btn["text"]
                await kv.set(msg["from"], str(rdi))

                # Any chance that the application crashed, was restarted, and some of the messages had already been sent?'
                ids = [i for i, fp in enumerate(rdi.reports) if Path(uploaded_data.file_path).name in fp]
                idx = ids[0]
                if not rdi.reports_status[idx] == "sent":
                    if btn["text"] == "Accept":
                        logger.info(f"Source phone number: {msg['from']}, report_id: {report_id}({type(report_id)})")
                        response = await messanger.send_progress_report(str(msg["from"]), str(report_id))
                        logger.debug(f"(MessageProcessor)  Response from sending a progress report message: {response}")

                        status = response["messages"][0]["message_status"]
                        logger.info(f"(MessageProcessor) Opt in status: {status}")
                        if status == "accepted":
                            rdi.reports_status[idx] = "sent"
                            await kv.set(msg["from"], str(rdi))

                            logger.info("The progress report was successfully sent to WA.")
                        else: # Server error
                            logger.error(f'Server error: {response["message"]}')
                            # TODO: Backoff using aiohttp library??
                            await kv.set(opt_in_id, str(uploaded_data))
                            #await asyncio.sleep(15)
                            #await r.publish(OPT_IN_RESPONSES, raw_msg)
                            #await r.xadd(OPT_IN_RESPONSES, raw_msg)
                            ct = datetime.now()
                            logger.debug(f"(MessageProcessors) Current time: {ct}")
                            run_date = ct + timedelta(seconds=30)
                            scheduler.add_job(func=async_publish, args=[r, OPT_IN_RESPONSES, raw_msg], trigger="date", run_date=run_date)
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
        #await r.publish(OPT_IN_RESPONSES, raw_msg)
        #await r.xadd(OPT_IN_RESPONSES, raw_msg)
        ct = datetime.now()
        logger.debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(seconds=30)
        scheduler.add_job(func=async_publish, args=[r, OPT_IN_RESPONSES, raw_msg], trigger="date", run_date=run_date)


def signature_preserving_decorator(processor, messanger: WhatsAppWrapper, r: redis.Redis, kv: redis.Redis):
    @functools.wraps(processor)
    async def wrapper(message):
        return await processor(r=r, kv=kv, messanger=messanger, message=message)
    return wrapper


async def process_messages():
    scheduler.start()

    r  = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
    kv = await redis.from_url("redis://localhost", db=REDIS_KV_STORE_DB)

    await r.flushall()
    await kv.flushall()

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
                    await asyncio.create_task(uploaded.asend(message))
                elif channel == PENDING_DELIVERY_FILENAMES:
                    await pending(message)
                elif channel == OPT_IN_RESPONSES:
                    await opt_in(message)



