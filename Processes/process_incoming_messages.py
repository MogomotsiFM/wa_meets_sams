import os
import re
import uuid
import json
import time
import asyncio
import logging
import mimetypes

import functools

import dataclasses
from typing import Callable, Any

from pathlib import Path

import redis.asyncio as redis
import redis.client as client

from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError, BusyLoadingError

from datetime import datetime, timedelta

from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore

from Messangers.wa_wrapper import WhatsAppWrapper

from Common.comms_data_structs import UploadedData, ReportDeliveryInfo, PendingDeliveryData, GradeReports

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger()

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")
REDIS_KV_STORE_DB = os.getenv("KV_STORE_DB")

PENDING_DELIVERY_FILENAMES = os.getenv("PENDING_DELIVERY_FILENAMES")
UPLOADED_ARTIFACTS = os.getenv("UPLOADED_ARTIFACTS")
OPT_IN_RESPONSES = os.getenv("OPT_IN_RESPONSES")

if PENDING_DELIVERY_FILENAMES is None or UPLOADED_ARTIFACTS is None or OPT_IN_RESPONSES is None:
    raise ValueError("All the three redis channel names should be define in environment variable.")

WA_SAMS_TOKEN = os.getenv("WA_SAMS_TOKEN")
WA_SAMS_PHONE_ID = os.getenv("WA_SAMS_PHONE_ID")
if WA_SAMS_TOKEN is None or WA_SAMS_PHONE_ID is None:
    raise ValueError("WA_SAMS_TOKEN and WA_SAMS_PHONE_ID environment variables should be set.")
else:
    logger.debug(f"(MessageProcessors)  token: {WA_SAMS_TOKEN}")
    logger.debug(f"(MessageProcessors)  Phone Id: {WA_SAMS_PHONE_ID}")

jobstores = {
    'default': RedisJobStore(
        host='localhost',
        port=6379,
        db=REDIS_PUBSUB_DB, # Use a specific database number
        jobs_key='apscheduler.jobs', # Custom key for jobs
        run_times_key='apscheduler.run_times' # Custom key for run times
    )
}
executors = {
    'default': ThreadPoolExecutor(100),
    'processpool': ProcessPoolExecutor(10)
}
job_defaults = {
    "misfire_grace_time": 30*60,
    #"max_instances":1
}
#scheduler = AsyncIOScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults)
scheduler = AsyncIOScheduler(jobstores=jobstores, job_defaults=job_defaults)

retry_strategy = Retry(ExponentialBackoff(cap=10, base=1), 3)

def init() -> WhatsAppWrapper:
    WA_SAMS_TOKEN = os.getenv("WA_SAMS_TOKEN")
    WA_SAMS_PHONE_ID = os.getenv("WA_SAMS_PHONE_ID")
    if WA_SAMS_TOKEN is None or WA_SAMS_PHONE_ID is None:
        raise ValueError("WA_SAMS_TOKEN and WA_SAMS_PHONE_ID environment variables should be set.")
    
    messanger = WhatsAppWrapper(bearer_token=WA_SAMS_TOKEN, phone_number_id=WA_SAMS_PHONE_ID)
    logger.debug(f"(MessageProcessors)  token: {WA_SAMS_TOKEN}")
    logger.debug(f"(MessageProcessors)  Phone Id: {WA_SAMS_PHONE_ID}")

    return messanger


async def async_publish(channel, message: str):
    r = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
    await r.publish(channel, message)


def safe_update(key, r: redis.Redis):
    with r.pipeline() as pipe:
        while True:
            try:
                # Watch the key for changes
                pipe.watch(key)
                # Read the current value
                current_value = pipe.get(key)
                
                # Perform application logic
                new_value = int(current_value or 0) + 1
                
                # Start transaction block
                pipe.multi()
                pipe.set(key, new_value)
                # Execute; fails if 'key' changed after 'watch'
                pipe.execute()
                break
            except redis.WatchError:
                # Key was modified, retry the operation
                continue


async def upload_data(r: redis.Redis, kv: redis.Redis, messanger: WhatsAppWrapper, message):
    """
    r: Used for pub-sub
    kv: Used as a key-value store
    """
    try:
        logger.info("(UploadData) About to upload an artifact")
        data = PendingDeliveryData.create( message["data"].decode() )
        file_path = data.file_path
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
                    grade = data.grade,
                    encrypted_enc_key=data.encrypted_enc_key,
                    send_retries = 0
                )
                no = await r.publish(UPLOADED_ARTIFACTS, str(msg))
                logger.info(f"Published to {UPLOADED_ARTIFACTS}: {msg}, no. of subscribers: {no}")
            else:
                ct = datetime.now()
                logger.debug(f"(MessageProcessors) Current time: {ct}")
                run_date = ct + timedelta(seconds=30)
                scheduler.add_job(func=async_publish, args=[PENDING_DELIVERY_FILENAMES, str(data)], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)
        else:
            error_msg = f"Artifact has unknown content type: {file_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    except Exception as exp:
        logger.error("(MessageProcessors) Failed to upload the an artifact.")
        logger.error(f"(MessageProcessors) Error: {exp}")
        # Put the file path back into the queue so we try uploading it again.
        ct = datetime.now()
        logger.debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(seconds=30)
        scheduler.add_job(func=async_publish, args=[PENDING_DELIVERY_FILENAMES, str(data)], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)


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
                            scheduler.add_job(func=async_publish, args=[UPLOADED_ARTIFACTS, str(message)], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)

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
                run_date = ct + timedelta(seconds=60)
                scheduler.add_job(func=async_publish, args=[UPLOADED_ARTIFACTS, str(message)], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)
        else:
            # TODO: Add the message to the dead letter queue
            logger.info(f"(MessageProcessor)  Message retried many times. It is possible that the phone number is not on WhatsApp.")

            rdi.reports_status[idx] = "unreachable"
            #await kv.set(msg["from"], str(rdi))
            # We add them to the list of parents for whom we must print progress reports.
            # We could also send a reminder a day before the day of collection.
            uploaded_data = message
            reports = await kv.get(uploaded_data.grade)
            if reports is None:
                gr = GradeReports( [uploaded_data.file_path], [uploaded_data.encrypted_enc_key] )
                await kv.set(uploaded_data.grade, str(gr))
            else:
                gr = GradeReports.create( reports.decode() )
                gr.add_report(uploaded_data.file_path, uploaded_data.encrypted_enc_key)
                await kv.set(uploaded_data.grade, str(gr))

    except Exception as exp:
        logger.info(f"(MessageProccessor) Could not send opt-in message to WhatsApp servers.")
        logger.info(f"(MessageProccessor)  Error: {exp}")
        message.send_retries = message.send_retries + 1
        ct = datetime.now()
        logger.debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(seconds=30)
        scheduler.add_job(func=async_publish, args=[UPLOADED_ARTIFACTS, str(message)], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)
    except BaseException as exp:
        logger.info(f"(MessageProccessor)  BaseException Error: {exp}")


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
                if rdi.reports_status[idx] == "not-sent":
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
                            await kv.set(opt_in_id, str(uploaded_data))
                            #await r.xadd(OPT_IN_RESPONSES, raw_msg)
                            ct = datetime.now()
                            logger.debug(f"(MessageProcessors) Current time: {ct}")
                            run_date = ct + timedelta(seconds=30)
                            scheduler.add_job(func=async_publish, args=[OPT_IN_RESPONSES, raw_msg], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)
                    elif btn["text"] == "Decline":
                        rdi.reports_status[idx] = "declined"
                        await kv.set(msg["from"], str(rdi))
                        # We add them to the list of parents for whom we must print progress reports.
                        # We could also send a reminder a day before the day of collection.
                        logger.debug(f"(MessageProcessor)  The parent chose to come to school to collect the report.")
                        reports = await kv.get(uploaded_data.grade)
                        if reports is None:
                            logger.info(f"(MessageProcessor) Adding the report to the grade {uploaded_data.grade} pile.")
                            gr = GradeReports( [uploaded_data.file_path], [uploaded_data.encrypted_enc_key] )
                            await kv.set(uploaded_data.grade, str(gr))
                        else:
                            gr = GradeReports.create( reports.decode() )
                            gr.add_report(uploaded_data.file_path, uploaded_data.encrypted_enc_key)
                            logger.info(f"(MessageProcessors) Adding another report to the grade {uploaded_data.grade} pile. Count: {len(gr.report_paths)}")
                            await kv.set(uploaded_data.grade, str(gr))
            else:
                raise ValueError("Incorrect message format. Expected a button field and none was found.")
    except Exception as exp:
        logger.info(f"(MessageProcessor) Error: {exp}")
        #await r.publish(OPT_IN_RESPONSES, raw_msg)
        #await r.xadd(OPT_IN_RESPONSES, raw_msg)
        ct = datetime.now()
        logger.debug(f"(MessageProcessors) Current time: {ct}")
        run_date = ct + timedelta(seconds=30)
        scheduler.add_job(func=async_publish, args=[OPT_IN_RESPONSES, raw_msg], trigger="date", run_date=run_date, id=f"{uuid.uuid4()}", replace_existing=False)
    except BaseException as exp:
        logger.info(f"(MessageProccessor)  BaseException Error: {exp}")


async def auto_decline():
    logging.getLogger().info("(MessageProcessors) Auto-declining opt-in messages.")

    for secs, job in enumerate(scheduler.get_jobs(), start=60):
        ct = datetime.now()
        run_date = ct + timedelta(seconds=secs)
        job.reschedule(trigger="date", run_date=run_date)

    #kv = await redis.from_url("redis://localhost", db=REDIS_KV_STORE_DB, decode_responses=True)
    kv = await redis.from_url(
        "redis://localhost",
        db=REDIS_KV_STORE_DB,
        decode_responses=True,
        retry=retry_strategy,
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError, asyncio.exceptions.CancelledError]
    )
    r  = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)

    async for key in kv.scan_iter(match='*', count=1):
        # We have at least three kv stores that co-exist. Two of them have decimal keys: phone number and grade.
        if key.isdecimal() and len(key)>=10: 
            logger.info(f"(MessageProcessor) Auto-declining the following message id: {key}?")
            value = await kv.get(key)
            rdi = ReportDeliveryInfo.create(value)
            if rdi.opt_in_status == "Unknown":
                logger.debug(f"(MessageProcessor) Auto-decline: Number of reports: {len(rdi.reports)}")
                rdi.opt_in_status = "Decline"
                await kv.set(key, str(rdi))

                msg = ReportDeliveryInfo.emulate_decision(key, rdi.opt_in_msg_id, "Decline")
                await r.publish(OPT_IN_RESPONSES, json.dumps(msg))


async def done():
    r  = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)

    # Ensure that there are no subscribers
    count  = await r.publish(PENDING_DELIVERY_FILENAMES, "STOP")
    count += await r.publish(UPLOADED_ARTIFACTS, "STOP")
    count += await r.publish(OPT_IN_RESPONSES, "STOP")
    if count:
        return False
 
    if len( scheduler.get_jobs() ) > 0:
        return False
    
    #kv = await redis.from_url("redis://localhost", db=REDIS_KV_STORE_DB, decode_responses=True)
    kv = await redis.from_url(
        "redis://localhost",
        db=REDIS_KV_STORE_DB,
        decode_responses=True,
        retry=retry_strategy,
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError, asyncio.exceptions.CancelledError]
    )

    async for key in kv.scan_iter(match='*', count=1):
        # We have at least three kv stores that co-exist. Two of them have decimal keys: phone number and grade.
        if key.isdecimal() and len(key)>=10:
            value = await kv.get(key)
            rdi = ReportDeliveryInfo.create(value)
            if rdi.opt_in_status == "Unknown":
                return False
            
            for status in rdi.reports_status:
                if status == "not-sent":
                    return False
            
    return True


def signature_preserving_decorator(processor, messanger: WhatsAppWrapper, r: redis.Redis, kv: redis.Redis):
    @functools.wraps(processor)
    async def wrapper(message):
        return await processor(r=r, kv=kv, messanger=messanger, message=message)
    return wrapper


async def handle_message(r: redis.Redis, pubsub, channel: str, message, processor: Callable[[str], Any], unsubscribed: dict):
    if message['data'].decode() == "STOP":
        await pubsub.unsubscribe(channel)
        unsubscribed[channel] = True
    else:
        await asyncio.create_task(processor(message))


async def process_messages(run_date: datetime):
    scheduler.remove_all_jobs()
    scheduler.start()

    r  = await redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
    kv = await redis.from_url(
        "redis://localhost", 
        db=REDIS_KV_STORE_DB, 
        retry=retry_strategy,
        retry_on_error=[BusyLoadingError, ConnectionError, TimeoutError, asyncio.exceptions.CancelledError]
    )

    await r.flushall()
    await kv.flushall()

    #messanger = init()

    async with WhatsAppWrapper(bearer_token=WA_SAMS_TOKEN, phone_number_id=WA_SAMS_PHONE_ID) as messanger:
        async with r.pubsub() as pubsub:
            pending = signature_preserving_decorator(upload_data, messanger, r, kv)
            uploaded = send_opt_in_messages(r=r, kv=kv, messanger=messanger)
            # The first message pushed into a generator has to be None.
            await uploaded.asend(None)
            opt_in = signature_preserving_decorator(handle_opt_in_responses, messanger, r, kv)

            await pubsub.subscribe(UPLOADED_ARTIFACTS, PENDING_DELIVERY_FILENAMES, OPT_IN_RESPONSES)

            unsubscribed: dict[str, bool] = {}

            async for message in pubsub.listen():
                if message['type'] == 'message':
                    logger.info(f"Message: {message}")
                    channel = message["channel"].decode()
                    if channel == UPLOADED_ARTIFACTS:
                        await handle_message(r, pubsub, UPLOADED_ARTIFACTS, message, uploaded.asend, unsubscribed)
                    elif channel == PENDING_DELIVERY_FILENAMES:
                        await handle_message(r, pubsub, PENDING_DELIVERY_FILENAMES, message, pending, unsubscribed)
                    elif channel == OPT_IN_RESPONSES:
                        await handle_message(r, pubsub, OPT_IN_RESPONSES, message, opt_in, unsubscribed)

                unsubed = unsubscribed.values()
                dn = await done()
                if ((datetime.now() > run_date) and dn) or (len(unsubed)==3 and all(unsubed)):
                    break
            await pubsub.close()

