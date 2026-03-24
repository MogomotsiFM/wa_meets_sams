import os
from typing import Dict
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass


@dataclass
class AppDirectories:
    db_path: str|None
    sams_path: Path
    reports_dir: Path
    # A directory that contains cover pages
    cover_pgs_dir: Path
    # A dictionary of cover pages for each phase.
    cover_pgs_paths: Dict[str, Path]
    school_emblem_path: Path
    logs_dir: Path
    dead_letter_dir: Path
    pending_delivery_dir: Path


def create_report_directories(sams_path, app_working_dir) -> AppDirectories:
    date = f"{datetime.now()}"
    date = date.replace(":", "T")

    app_working_dir = Path(os.path.join(app_working_dir, "Reports", date) )

    cover_pg_dir = Path( os.path.join(app_working_dir, "covers") )
    reports_dir = Path( os.path.join(app_working_dir, "reports") )
    log_dir = Path( os.path.join(app_working_dir, "logs") )

    dead_letter_dir = Path( os.path.join(app_working_dir, "dead_letter") )
    pending_delivery_dir = Path( os.path.join(app_working_dir, "pending_delivery") )

    os.makedirs(name=cover_pg_dir, exist_ok=True)
    os.makedirs(name=reports_dir, exist_ok=True)
    os.makedirs(name=dead_letter_dir, exist_ok=True)
    os.makedirs(name=pending_delivery_dir, exist_ok=True)
    os.makedirs(name=log_dir, exist_ok=True)
    
    return AppDirectories(
        db_path=None,
        sams_path=sams_path,
        reports_dir=reports_dir,
        cover_pgs_dir=cover_pg_dir,
        cover_pgs_paths={},
        school_emblem_path="",
        logs_dir=log_dir,
        dead_letter_dir=dead_letter_dir,
        pending_delivery_dir=pending_delivery_dir
    )