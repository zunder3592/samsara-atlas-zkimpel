import json
import os
from sqlalchemy.orm import Session

from app.storage.database import SessionLocal
from app.storage.models import EmployeeRecord, CaseNote


def retrieve_employee_context(employee_id: str) -> dict:
    """Retrieve employee metadata and recent HR interactions from the HRIS."""
    db = SessionLocal()
    try:
        emp = db.query(EmployeeRecord).filter_by(employee_id=employee_id).first()
        if not emp:
            return {
                "employee_id": employee_id,
                "metadata": {},
                "last_activities": [],
                "found": False,
            }
        return {
            "employee_id": emp.employee_id,
            "metadata": json.loads(emp.metadata_json or "{}"),
            "last_activities": json.loads(emp.last_activities_json or "[]"),
            "found": True,
        }
    finally:
        db.close()


def post_case_note_to_hris(case_id: int, employee_id: str, note: str) -> dict:
    """Write a case note row to the HRIS. Can create duplicate rows on retry (intentional flaw, see P003)."""
    db = SessionLocal()
    try:
        case_note = CaseNote(
            case_id=case_id,
            employee_id=employee_id,
            note=note,
        )
        db.add(case_note)
        db.commit()
        db.refresh(case_note)
        return {"id": case_note.id, "employee_id": employee_id, "note": note[:100]}
    finally:
        db.close()
