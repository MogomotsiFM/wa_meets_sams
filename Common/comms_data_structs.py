import json
import dataclasses

from pathlib import Path
from typing import List, Literal

OptInDecision = Literal["Unknown", "Accept", "Decline"]
 
ReportDeliveryStatus = Literal["sent", "not-sent", "declined", "auto-declined", "unreachable"]


@dataclasses.dataclass
class UploadedData:
    upload_id: str
    file_path: Path
    grade: str
    # Unique message index
    index: int
    encrypted_enc_key: str
    send_retries: int = 0
    # We were able to send an opt-in message to this number
    phone_number: str = "not-set"
    report_delivery_status: ReportDeliveryStatus = "not-sent"
    
    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)

    @staticmethod
    def create(data: str):
        j = json.loads(data)
        return UploadedData(**j)


@dataclasses.dataclass
class PendingDeliveryData:
    file_path: str
    grade: str
    encrypted_enc_key: str
    # Unique message index
    index: int = -1
    uploaded_data: UploadedData

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)
    
    @staticmethod
    def create(data: str):
        j = json.loads(data)
        pdd = PendingDeliveryData(**j)
        uploaded_data = UploadedData(pdd.uploaded_data)
        pdd.uploaded_data = uploaded_data
        return pdd


@dataclasses.dataclass
class GradeReports:
    # List of reports for a particular grade for in-person collection
    report_paths: List[Path]
    encryption_keys: List[str]
    unique_indices: List[int]
    uploaded_data: List[UploadedData] = dataclasses.field(default_factory=list)

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)
    
    @staticmethod
    def create(data: str):
        j = json.loads(data)
        grade_reports =  GradeReports(**j)
        uploaded_data = [UploadedData(ud) for ud in grade_reports.uploaded_data]
        grade_reports.uploaded_data = uploaded_data
        return grade_reports
    
    def add_report(self, report_path: Path, encryption_key: str, index: int):
        self.report_paths.append(report_path)
        self.encryption_keys.append(encryption_key)
        self.unique_indices.append(index)
        return self
    
    def add_uploaded_data(self, uploaded_data: UploadedData):
        self.uploaded_data.append(uploaded_data)
        return self


@dataclasses.dataclass
class ReportDeliveryInfo:
    opt_in_status: OptInDecision
    #phone_number: str
    opt_in_msg_id: str
    # It is possible that a parent has multiple kids at a school
    # This keeps the list of reports associated with that parent's phone number
    reports: List[Path] #= dataclasses.field(default_factory=List)
    reports_status: List[ReportDeliveryStatus] #= dataclasses.field(default_factory=List)
    unique_indices: List[int] #= dataclasses.field(default_factory=lambda:[-1])
    uploaded_data: List[UploadedData] = dataclasses.field(default_factory=list)

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)

    @staticmethod
    def create(data: str):
        j = json.loads(data)
        rdi = ReportDeliveryInfo(**j)
        uploaded_data = [UploadedData(ud) for ud in rdi.uploaded_data]
        rdi.uploaded_data = uploaded_data
        return rdi

    def add_report(self, report_path: Path, index: int, report_status: ReportDeliveryStatus = "not-sent"):
        self.reports.append(report_path)
        self.reports_status.append(report_status)
        self.unique_indices.append(index)
        return self
    
    def add_uploaded_data(self, uploaded_data: UploadedData):
        self.uploaded_data.append(uploaded_data)
        return self

    @staticmethod
    def emulate_decision(parent_tel: str, opt_in_msg_id: str, decision: OptInDecision, context_from: Literal["WA", "self"]):
        """
        opt_in_msg_id: Will be used to lookup the report upload id so that it may be send to the parent

        context_from: In a real message, this would be the WA phone number of the school(the number that sent 
                      the original opt-in message). Here, we use it to differentiate between declining opt-in messages
                      ourselves("self") at the deadline, or genuine response from guardians via WhatsApp("WA")
        """
        msg = [
            {
                "context":{
                    "from":context_from,
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

