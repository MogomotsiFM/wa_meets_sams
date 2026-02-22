import os
import logging

from pathlib import Path

from dataclasses import dataclass

import pandas as pd

from pypdf import PdfReader, PdfWriter,PageObject as Page

from join_tables import join_tables


def load_cover_page(grade: str, cover_pg_dir: str):
    phase = "FET" if grade in ["Grade 10", "Grade 11", "Grade 12"] else "Senior" if grade in ["Grade 7", "Grade 8", "Grade 9"] else "Junior"
    cover_page_path = os.path.join(cover_pg_dir, f"{phase}_report_cover.pdf")
    reader = PdfReader(cover_page_path)
    return reader.pages[0]


def name_file(learner: pd.DataFrame) -> tuple[str, bool]:
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
    if len(learner['Tel1']) >= 10:
        filename += f" - Tel{learner['Tel1']}"
        contact_number_exists = True
    if len(learner['Tel2']) >= 10:
        filename += f" - Tel{learner['Tel2']}"
        contact_number_exists = True
    if len(learner['Tel3']) >= 10:
        filename += f" - Tel{learner['Tel3']}"
        contact_number_exists = True
    if len(learner['EMail']) > 0:
        filename += f" - EMail{learner['EMail']}"
    
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
        key = f"{learner['FName'].capitalize()}{learner['SName'].capitalize()}"
        if len(learner['SecondName']) > 0:
            key = f"{learner['FName'].capitalize()}{learner['SecondName'].capitalize()}{learner['SName'].capitalize()}"
        return key


def extract_learner_name(text: str) -> tuple[str, str|None, str]:
    """
    Extract the learner's name from the text.
    The expected format is "learner: surname, names" where names can be one or
    two names (first name and second name).

    PRE-CONDITION: All the text should be in lowercase.
    """
    learner_name = ""
    for line in text.split('\n'):
        if "learner: " in line:
            learner_name = line.replace("learner: ", "").strip()
            break

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
    encryption_key: str|None


def process_pdf_by_learner(pages: list[Page], dataframe: pd.DataFrame):
    """
    Split PDF into pages and extract learner names for file naming.
    """
    for page in pages:
        text = page.extract_text().lower()
        
        admission_no = extract_information(text, "admission no:")
        # if the admission number is found, we can use it to lookup the learner in the dataframe
        if admission_no:
            print(f"Found admission number: {admission_no}")
            learner_info = dataframe[dataframe['AccessionNo'] == admission_no].iloc[0]
        else:
            print("No admission number found, using learner information to uniquely identify the learner")
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
                print(f"Multiple learners found for {firstname} {second_name} {surname} with birth date {birth_date}.")
            
            learner_info = learner_info.iloc[0]

        filename, contact_number_exists = name_file(learner_info)
        key = generate_encryption_key(learner_info)

        if contact_number_exists:
            # It is likely that we will send the report via WhatsApp if a contact number exists.
            #writer.encrypt(str(key))
            yield LearnerReport(report=page, filename=filename, encryption_key=key)
        else:
            yield LearnerReport(report=page, filename=filename, encryption_key=None)


def process_reports(db_path, reports_path, cover_pg_path, dead_letter_dir, pending_delivery_dir):
    _, joined_table = join_tables(db_path)
    print("Joined table data:", joined_table)
    dataframe = pd.DataFrame(joined_table)

    for report_path in reports_path.iterdir():
        if report_path.is_file() and report_path.suffix.lower() == ".pdf":
            reader = PdfReader(report_path)
            print(f"Processing PDF: {report_path.name}")

            grade = report_path.name.split("_")[0]

            cover_page = load_cover_page(grade, cover_pg_path)

            reports = process_pdf_by_learner(reader.pages, dataframe)
            for learner_report in reports:
                writer = PdfWriter()
                writer.add_page(cover_page)
                writer.add_page(learner_report.report)
                if learner_report.encryption_key:
                    writer.encrypt(learner_report.encryption_key)
                    output_path = os.path.join(pending_delivery_dir, f"{learner_report.filename}.pdf")
                else:
                    output_path = os.path.join(dead_letter_dir, f"{learner_report.filename}.pdf")

                with open(output_path, 'wb') as f:
                    writer.write(f)
                
                print(f"Saved report: {learner_report.filename} with key: {learner_report.encryption_key}")


if __name__ == "__main__":
    db_path = "TestingDB.mdb"

    root_dir = "C:\\Users\GAME\\Desktop\\EdusolSAMS\\reports\\2026-02-20 22T58T10.473443"
    dead_letter_dir = os.path.join(root_dir, "dead_letter")
    if not os.path.exists(dead_letter_dir):
        os.makedirs(dead_letter_dir)

    pending_delivery_dir = os.path.join(root_dir, "pending_delivery")
    if not os.path.exists(pending_delivery_dir):
        os.makedirs(pending_delivery_dir)

    reports_dir_ = os.path.join(root_dir, "Reports")
    reports_path = Path(reports_dir_)

    cover_pg_dir = os.path.join(root_dir, "covers")
    process_reports(db_path, reports_path, cover_pg_dir, dead_letter_dir, pending_delivery_dir)
