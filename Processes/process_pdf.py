import os
import re
import asyncio
import json
import logging

from pathlib import Path

import redis.asyncio as redis

from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError, BusyLoadingError

from typing import Dict, List, get_args
from dataclasses import dataclass

import pandas as pd

from pypdf import PdfReader, PdfWriter, PageObject as Page

from .join_tables import join_tables

from Common.comms_data_structs import PendingDeliveryData, GradeReports, UploadedData, ReportDeliveryStatus, ReportDeliveryInfo

from dotenv import load_dotenv
load_dotenv()

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")
REDIS_KV_STORE_DB = os.getenv("KV_STORE_DB")

def load_cover_page(grade: str, cover_pg_dir: str, cover_pgs: Dict[str, Path]):
    # TODO: Use memoization.
    phase = "FET" if grade.capitalize() in ["10", "11", "12"] else "Senior" if grade in ["7", "8", "9"] else "Intermediate" if grade in ["4", "5", "6"] else "Foundation"
    if len(cover_pg_dir) > 0:
        cover_page_path = os.path.join(cover_pg_dir, f"{phase}_report_cover.pdf")
    else:
        cover_page_path = cover_pgs[phase]
    reader = PdfReader(cover_page_path)
    return reader.pages[0]


def is_valid_number(phone_number: str):
    return len(phone_number) >= 10 and phone_number.isdigit()


def name_file(learner: pd.Series) -> tuple[str, bool]:
    """
    Create a filename based on the learner's information.
    """
    learner['Tel1'] = (learner['Tel1Code'] + learner['Tel1'])
    learner['Tel2'] = (learner['Tel2Code'] + learner['Tel2'])
    # For some reason, Tel3Code is null by default, while every missing value is an empty string.
    if pd.notna(learner['Tel3Code']) and learner['Tel3Code'].isdigit():
        learner['Tel3'] = (learner['Tel3Code'] + learner['Tel3'])
    
    filename = learner['FName']
    if len(learner['SecondName']) > 0:
        filename += f" {learner['SecondName']}"
    filename += f" {learner['SName']}"

    contact_number_exists = False
    headers = learner.index.to_list()
    if is_valid_number(learner['Tel1']):
        filename += f" - Tel{learner['Tel1']}"
        contact_number_exists = True
    if is_valid_number(learner['Tel2']):
        filename += f" - Tel{learner['Tel2']}"
        contact_number_exists = True
    if is_valid_number(learner['Tel3']):
        filename += f" - Tel{learner['Tel3']}"
        contact_number_exists = True
    if 'SpouseCell' in headers and is_valid_number(learner['SpouseCell']):
        filename += f" - Tel{learner['SpouseCell']}"
        contact_number_exists = True
    if 'SpouseCell' in headers and is_valid_number(learner['SpouseWorkTel']):
        filename += f" - Tel{learner['SpouseWorkTel']}"
        contact_number_exists = True
    if 'EMail' in headers and len(learner['EMail']) > 0:
        filename += f" - EMail{learner['EMail']}"
    if 'SpouseEmail' in headers and len(learner['SpouseEmail']) > 0:
        filename += f" - Email{learner['SpouseEmail']}"
    logging.getLogger().debug(f"Progress report filename: {filename}")
    return filename, contact_number_exists


def generate_encryption_key(learner: pd.Series) -> str:
    """
    Generate an encryption key based on the learner's ParentIDNo or SpouseID.
    If both are missing, generate a key from the learner's name.
    """
    if len(learner['ParentIDNo']) > 0:
        return learner['ParentIDNo']
    elif len(learner['SpouseID']) > 0:
        return learner['SpouseID']
    else:
        first = learner['FName'].capitalize()
        second = learner['SecondName'].capitalize().replace(" ", "")
        surname = learner['SName'].capitalize().replace(" ", "")
        key = f"{first}{surname}"
        if len(second) > 0:
            key = f"{first}{second}{surname}"
        return key


def extract_learner_name(text: str) -> tuple[str, str, str]:
    """
    Extract the learner's name from the text.
    The expected format is "learner: surname, names" where names can be one or
    two names (first name and second name).

    PRE-CONDITION: All the text should be in lowercase.
    """
    learner_name = ""
    for line in text.split('\n'):
        # TODO: Find a more robust way to extract the learner's name. 
        if "learner: " in line:
            learner_name = line.replace("learner: ", "").strip()
            break
    
    if learner_name == "":
        logging.getLogger().error("Learner name not found in the report.")
        raise ValueError("Learner name not found in the report.")
    
    surname, names_ = learner_name.split(",")
    names = names_.strip().split(" ")

    first_name = names[0].strip()
    if len(names) > 1:
        second_name = names[1].strip()
    else:
        second_name = ""

    first_name = first_name.strip()
    second_name = second_name.strip()
    surname = surname.strip()

    return first_name, second_name, surname


def extract_information(text: str, pattern: str) -> str|None:
    """
    Extract information from the text based on a pattern.
    """
    extracted_info: str|None = None
    for line in text.split('\n'):
        if pattern in line:
            extracted_info = line.replace(pattern, "").strip()
            break
    return extracted_info


@dataclass
class LearnerReport:
    report: Page
    filename: str
    grade: str
    encryption_key: str|None


def raise_exception(exp: Exception):
    raise exp


def process_pdf_by_learner(pages: list[Page], dataframe: pd.DataFrame):
    """
    Split PDF into pages and extract learner names for file naming.
    """
    for page in pages:
        text = page.extract_text().lower()
        
        grade = extract_information(text, "grade")
        # We need to handle this exception better. At the moment we swallow it.
        grade = re.findall(r"\d+", grade)[0] if grade else raise_exception(ValueError("Grade not found in the report."))

        admission_no = extract_information(text, "admission no:")
        # If the admission number is found, we can use it to lookup the learner in the dataframe
        if admission_no:
            logging.getLogger().debug(f"Found admission number: {admission_no}")
            learner_info = dataframe[dataframe['AccessionNo'] == admission_no].iloc[0]
        else:
            logging.getLogger().debug("No admission number found, using learner information to uniquely identify learners.")
            firstname, second_name, surname = extract_learner_name(text)
            birth_date = extract_information(text, "birth date:")
            birth_date = birth_date.replace("/", "") if birth_date else None

            # Lookup learner in dataframe and use all the data as part of the filename
            # Exclude the LearnerIDNo and ParentIDNo columns from the filename
            # We want to use as much information as possible to make sure we find only one match in the dataframe
            learner_info = dataframe[
                (dataframe['FName'].str.lower() == firstname) & 
                (dataframe['SecondName'] == second_name) & 
                (dataframe['SName'].str.lower() == surname) &
                # TODO: Find a better way to compare dates that are in different formats. 
                # They could break our app just by changing the date format.
                #  Look into python-dateutil package to parse dates in different formats and compare them.
                (dataframe['BirthDate'].str.replace("/", "") == birth_date)
            ]#.iloc[0]

            if learner_info.size > 1:
                logging.getLogger().error(f"Multiple learners found for {firstname} {second_name} {surname} with birth date {birth_date}.")
            
            learner_info = learner_info.iloc[0]

        filename, contact_number_exists = name_file(learner_info)
        key = generate_encryption_key(learner_info)

        if contact_number_exists:
            # It is likely that we will send the report via WhatsApp if a contact number exists.
            #writer.encrypt(str(key))
            yield LearnerReport(report=page, filename=filename, grade=grade, encryption_key=key)
        else:
            yield LearnerReport(report=page, filename=filename, grade=grade, encryption_key=None)


async def process_reports(db_path: str, 
                    reports_dir: Path,
                    cover_pg_dir: Path,
                    cover_pgs: Dict[str, Path],
                    school_emblem_path: Path,
                    dead_letter_dir: Path,
                    pending_delivery_dir: Path
                ):
    logging.getLogger().info("Starting report processing...")
    status, joined_table = join_tables(db_path)
    if status == False:
        logging.getLogger().error(joined_table)
        raise ValueError(joined_table)
    logging.getLogger().debug(f"Joined table data: {json.dumps(joined_table, indent=2)}")
    dataframe = pd.DataFrame(joined_table)

    r = redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
    kv = redis.from_url("redis://localhost", db=REDIS_KV_STORE_DB)

    # The first message should be the path to the school emblem
    PENDING_DELIVERY_FILENAMES = os.getenv("PENDING_DELIVERY_FILENAMES")
    ud = UploadedData(upload_id="", file_path=school_emblem_path, grade="", index=-1, encrypted_enc_key="")
    d = PendingDeliveryData(file_path=school_emblem_path, grade="", encrypted_enc_key="", uploaded_data=ud)
    await r.publish(PENDING_DELIVERY_FILENAMES, str(d))

    index = 0
    for report_path in reports_dir.iterdir():
        if report_path.is_file() and report_path.suffix.lower() == ".pdf":
            reader = PdfReader(report_path)
            logging.getLogger().info(f"Processing PDF: {report_path.name}")

            grade = report_path.name.split("_")[0]

            reports = process_pdf_by_learner(reader.pages, dataframe)
            for report in reports:
                logging.getLogger().debug(f"Filename: {report.filename}, Grade: {report.grade} vs {grade}")
                writer = PdfWriter()
                try:
                    cover_page = load_cover_page(report.grade, cover_pg_dir, cover_pgs)
                
                    writer.add_page(cover_page)
                except Exception as exp:
                    logging.getLogger().debug(f"Cover page for grade {report.grade} was not found. All reports in this grade will not have cover pages.")

                writer.add_page(report.report)
                index+=1
                if report.encryption_key:
                    writer.encrypt(report.encryption_key)
                    output_path = os.path.join(pending_delivery_dir, f"{report.filename}.pdf")

                    ud = UploadedData(upload_id="", file_path=output_path, grade=report.grade, index=index, encrypted_enc_key=report.encryption_key, send_retries=0)
                    d = PendingDeliveryData(file_path=output_path, grade=report.grade, encrypted_enc_key=report.encryption_key, index=index, uploaded_data=ud)
                    await r.publish(PENDING_DELIVERY_FILENAMES, str(d))
                else:
                    output_path = os.path.join(dead_letter_dir, f"{report.filename}.pdf")
                    uploaded_data = UploadedData(upload_id="", file_path=output_path, grade=report.grade, index=index, encrypted_enc_key="", send_retries=0)
                    data = await kv.get(report.grade)
                    if data is None:
                        gr = GradeReports( report_paths=[output_path], encryption_keys=[""], unique_indices=[index], uploaded_data=[uploaded_data] )
                        await kv.set(report.grade, str(gr))
                    else:
                        gr = GradeReports.create(data.decode())
                        gr.add_report(output_path, "", index)
                        gr.add_uploaded_data(uploaded_data)
                        await kv.set(report.grade, str(gr))

                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                logging.getLogger().info(f"Saved report: {report.filename} with key: {report.encryption_key}")


async def process_dead_letter_queue(kv: redis.Redis, dead_letter_dir: Path, reports_dir: Path):
    """
    This function could also live in the process messages scope.
    But it needs a PDF writer, the encryption package, and the encryption key used to encrypt progress report
    encryption keys.
    So, it lives here
    """
    logging.getLogger().info("(ProcessPDF) Generating print-friendly report dossiers.")

    report: Dict[ReportDeliveryStatus, Dict[int, int]] = {k: {} for k in get_args(ReportDeliveryStatus)}

    async for key in kv.scan_iter(match='*', count=1):
        try:
            key = key.decode()
            if key.isdigit():
                data = await kv.get(key)
                data = data.decode()

                if len(key) <= 2:
                    gr = GradeReports.create(data)
                    report = generate_report(gr.uploaded_data, report)

                    writer = PdfWriter()
                    for report_path, enc_key in zip(gr.report_paths, gr.encryption_keys):
                        reader = PdfReader(report_path)
                        if reader.is_encrypted:
                            # Decrypt the encryption key
                            reader.decrypt(enc_key)

                        # The last page is the report itself. The first page could be the cover page.
                        writer.add_page(reader.pages[-1])

                    output = os.path.join(dead_letter_dir, f"grade_{key}.pdf")
                    with open(output, 'wb') as f:
                        writer.write(f)
                else: # Key is a phone number
                    rds = ReportDeliveryInfo.create(data)
                    if rds.opt_in_status == "Accept":
                        assert rds.uploaded_data[0].report_delivery_status=="sent", "The report delivery status of an accepted opt-in request should be 'sent'"
                        report = generate_report(rds.uploaded_data, report)

        except Exception as exp:
            logging.getLogger().debug(f"(ProcessorPDF) Error: {exp}")

    save_report(report, reports_dir)


def generate_report(grade_reports: List[UploadedData], report: Dict[ReportDeliveryStatus, Dict[int, int]]):
    for ud in grade_reports:
        rpt = report.setdefault(ud.report_delivery_status, {})
        count = rpt.setdefault(ud.grade, 0) + 1
        rpt[ud.grade] = count
        report[ud.report_delivery_status] = rpt
    return report


def save_report(report: Dict[ReportDeliveryStatus, Dict[int, int]], reports_dir: Path):
    df = pd.DataFrame(report)
    df.columns = df.columns.str.title()
    df.fillna(0, inplace=True)
    df = df.astype(int)
    df.sort_index(inplace=True)

    df["Total"] = df.sum(axis=1)
    total = pd.DataFrame([df.sum()], index=["Total"])
    df = pd.concat([df, total])

    report_path = os.path.join(reports_dir, "report.csv")
    df.to_csv(report_path, index_label="Grade")
    try:
        report_path = os.path.join(reports_dir, "report.xsl")
        df.to_excel(report_path, index_label="grade")
    except Exception:
        logging.getLogger().info("(ProcessPDF) Could not write the report to Excel.")


if __name__ == "__main__":
    db_path = "TestingDB.mdb"

    root_dir = "C:\\Users\\GAME\\Desktop\\Projects\\whatsapp_sams\\Reports\\2026-03-04 06T44T31.975026"
    dead_letter_dir = Path( os.path.join(root_dir, "dead_letter") )
    os.makedirs(dead_letter_dir, exist_ok=True)

    pending_delivery_dir = Path( os.path.join(root_dir, "pending_delivery") )
    os.makedirs(pending_delivery_dir, exist_ok=True)

    reports_dir_ = os.path.join(root_dir, "Reports")
    reports_path = Path(reports_dir_)

    cover_pg_dir = Path( os.path.join(root_dir, "covers") )
    school_emblem_path = Path("C:\\Users\\GAME\\Desktop\\Projects\\whatsapp_sams\\Data\\school_emblem.png")
    asyncio.run(
        process_reports(
            db_path=db_path, 
            reports_dir=reports_path, 
            cover_pg_dir=cover_pg_dir, 
            school_emblem_path=school_emblem_path, 
            dead_letter_dir=dead_letter_dir, 
            pending_delivery_dir=pending_delivery_dir
        )
    )
    
    
