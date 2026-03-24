import json
import dataclasses

from pathlib import Path
from typing import List, Literal

OptInDecision = Literal["Unknown", "Accept", "Decline"]
 
ReportDeliveryStatus = Literal["sent", "not-sent", "declined", "unreachable"]

@dataclasses.dataclass
class PendingDeliveryData:
    file_path: str
    grade: str
    encrypted_enc_key: str

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)
    
    @staticmethod
    def create(data: str):
        j = json.loads(data)
        return PendingDeliveryData(**j)


@dataclasses.dataclass
class GradeReports:
    # List of reports for a particular grade for in-person collection
    report_paths: List[str]
    encryption_keys: List[str]

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)
    

    @staticmethod
    def create(data: str):
        j = json.loads(data)
        return GradeReports(**j)
    
    def add_report(self, report_path: str, encryption_key: str):
        self.report_paths.append(report_path)
        self.encryption_keys.append(encryption_key)
        return self


@dataclasses.dataclass
class UploadedData:
    upload_id: str
    file_path: Path
    grade: str
    encrypted_enc_key: str
    send_retries: int

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)

    @staticmethod
    def create(data: str):
        j = json.loads(data)
        return UploadedData(**j)


@dataclasses.dataclass
class ReportDeliveryInfo:
    opt_in_status: OptInDecision
    #phone_number: str
    opt_in_msg_id: str
    # It is possible that a parent has multiple kids at a school
    # This keeps the list of reports associated with that parent's phone number
    reports: List[Path]
    reports_status: List[ReportDeliveryStatus]

    def __str__(self):
        d = dataclasses.asdict(self)
        return json.dumps(d)

    @staticmethod
    def create(data: str):
        j = json.loads(data)
        obj = ReportDeliveryInfo(**j)
        return obj

    def add_report(self, report_path: Path, report_status: ReportDeliveryStatus = "not-sent"):
        self.reports.append(report_path)
        self.reports_status.append(report_status)
        return self

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

