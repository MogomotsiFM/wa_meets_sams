import os
import re
import asyncio
import logging

from pathlib import Path

import redis.asyncio as redis

from dataclasses import dataclass

import pandas as pd

from pypdf import PdfReader, PdfWriter, PageObject as Page

from .join_tables import join_tables

from Common.comms_data_structs import PendingDeliveryData, GradeReports

from dotenv import load_dotenv
load_dotenv()

REDIS_PUBSUB_DB = os.getenv("PUBSUB_DB")
REDIS_KV_STORE_DB = os.getenv("KV_STORE_DB")

def load_cover_page(grade: str, cover_pg_dir: str):
    # TODO: Use memoization.
    phase = "FET" if grade.capitalize() in ["10", "11", "12"] else "Senior" if grade in ["8", "9"] else "Junior"
    cover_page_path = os.path.join(cover_pg_dir, f"{phase}_report_cover.pdf")
    reader = PdfReader(cover_page_path)
    return reader.pages[0]


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
    if len(learner['Tel1']) >= 10:
        filename += f" - Tel{learner['Tel1']}"
        contact_number_exists = True
    if len(learner['Tel2']) >= 10:
        filename += f" - Tel{learner['Tel2']}"
        contact_number_exists = True
    if len(learner['Tel3']) >= 10:
        filename += f" - Tel{learner['Tel3']}"
        contact_number_exists = True
    if 'SpouseCell' in headers and len(learner['SpouseCell']) >= 10:
        filename += f" - Tel{learner['SpouseCell']}"
        contact_number_exists = True
    if 'SpouseCell' in headers and len(learner['SpouseWorkTel']) >= 10:
        filename += f" - Tel{learner['SpouseWorkTel']}"
        contact_number_exists = True
    if 'EMail' in headers and len(learner['EMail']) > 0:
        filename += f" - EMail{learner['EMail']}"
    if 'SpouseEmail' in headers and len(learner['SpouseEmail']) > 0:
        filename += f" - Email{learner['SpouseEmail']}"
    logging.getLogger().debug(f"Progress report filename: {filename}")
    return filename, contact_number_exists


def generate_encryption_key(learner: pd.DataFrame) -> str:
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
                    school_emblem_path: Path,
                    dead_letter_dir: Path,
                    pending_delivery_dir: Path
                ):
    logging.getLogger().info("Starting report processing...")
    _, joined_table = join_tables(db_path)
    logging.getLogger().debug(f"Joined table data: {joined_table}")
    dataframe = pd.DataFrame(joined_table)

    r = redis.from_url("redis://localhost", db=REDIS_PUBSUB_DB)
    kv = redis.from_url("redis://localhost", db=REDIS_KV_STORE_DB)

    # The first message should be the path to the school emblem
    PENDING_DELIVERY_FILENAMES = os.getenv("PENDING_DELIVERY_FILENAMES")
    d = PendingDeliveryData(school_emblem_path, "", "")
    await r.publish(PENDING_DELIVERY_FILENAMES, str(d))

    for report_path in reports_dir.iterdir():
        if report_path.is_file() and report_path.suffix.lower() == ".pdf":
            reader = PdfReader(report_path)
            logging.getLogger().info(f"Processing PDF: {report_path.name}")

            grade = report_path.name.split("_")[0]

            reports = process_pdf_by_learner(reader.pages, dataframe)
            for report in reports:
                logging.getLogger().debug(f"Filename: {report.filename}, Grade: {report.grade} vs {grade}")
                cover_page = load_cover_page(report.grade, cover_pg_dir)
                
                writer = PdfWriter()
                writer.add_page(cover_page)
                writer.add_page(report.report)
                if report.encryption_key:
                    writer.encrypt(report.encryption_key)
                    output_path = os.path.join(pending_delivery_dir, f"{report.filename}.pdf")

                    d = PendingDeliveryData(output_path, report.grade, report.encryption_key)
                    await r.publish(PENDING_DELIVERY_FILENAMES, str(d))
                else:
                    output_path = os.path.join(dead_letter_dir, f"{report.filename}.pdf")
                    data = await kv.get(report.grade)
                    if data is None:
                        gr = GradeReports( [output_path], [""] )
                        await kv.set(report.grade, str(gr))
                    else:
                        gr = GradeReports.create(data.decode())
                        gr.add_report(output_path, "")
                        await kv.set(report.grade, str(gr))

                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                logging.getLogger().info(f"Saved report: {report.filename} with key: {report.encryption_key}")


async def process_dead_letter_queue(dead_letter_dir: Path):
    """
    This function could also live in the process messages scope.
    But it needs a PDF writer, the encryption package, and the encryption key used to encrypt progress report
    encryption keys.
    So, it lives here
    """
    logging.getLogger().info("(ProcessPDF) Generating print-friendly report dossiers.")

    kv = redis.from_url("redis://localhost", db=REDIS_KV_STORE_DB, decode_responses=True)
    
    counts = {}

    async for key in kv.scan_iter(match='*', count=1):
        try:
            key = int(key)
            writer = PdfWriter()

            data = await kv.get(key)
            gr = GradeReports.create(data)

            counts[key] = len(gr.report_paths)

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
        except Exception as exp:
            logging.getLogger().debug(f"(ProcessorPDF) Error: {exp}")

    for k, v in counts.items():
        logging.getLogger().info(f"(ProcessPDF) Expected Grade {k} parents: {v}")


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
    
    
