from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal

from app.engine.runner import run_workflow, IdempotencyConflict
from app.storage.database import SessionLocal
from app.storage.models import Case, Step, CaseNote, EmployeeRecord

import os

router = APIRouter()


@router.get("/employees")
def list_employees():
    db = SessionLocal()
    try:
        employees = db.query(EmployeeRecord).all()
        return {"employees": [e.employee_id for e in employees]}
    finally:
        db.close()


@router.get("/info")
def get_info():
    """Returns current provider type - use to verify Ollama is active."""
    return {"provider": os.getenv("PROVIDER_TYPE", "stub")}


@router.get("/cases")
def list_cases():
    db = SessionLocal()
    try:
        cases = db.query(Case).order_by(Case.id.desc()).limit(50).all()
        return {"case_ids": [c.id for c in cases]}
    finally:
        db.close()


class CaseInputsRequest(BaseModel):
    employee_id: str
    case_transcript: str
    tone: Literal["empathetic", "direct", "formal"]


class CreateCaseRequest(BaseModel):
    inputs: CaseInputsRequest
    idempotency_key: Optional[str] = None


@router.post("/cases")
def create_case(req: CreateCaseRequest):
    try:
        result = run_workflow(
            inputs=req.inputs.model_dump(),
            idempotency_key=req.idempotency_key,
        )
        return result
    #new conflict raised if someone enters a new desc/emp ID with a previous idempotency key
    except IdempotencyConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()  # prints full case transcript/context to stdout on failure, see P017
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}")
def get_case(case_id: int):
    db = SessionLocal()
    try:
        case = db.query(Case).filter_by(id=case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        steps = db.query(Step).filter_by(case_id=case_id).all()
        case_notes = db.query(CaseNote).filter_by(case_id=case_id).all()
        return {
            "case": {
                "id": case.id,
                "status": case.status,
                "inputs": case.inputs_json,
                "artifacts": case.artifacts_json,
                "outputs": case.outputs_json,
            },
            "steps": [
                {
                    "id": s.id,
                    "name": s.name,
                    "status": s.status,
                    "started_at": str(s.started_at) if s.started_at else None,
                    "finished_at": str(s.finished_at) if s.finished_at else None,
                    "attempts": s.attempts,
                    "output": s.output_json,
                    "error": s.error,
                }
                for s in steps
            ],
            "case_notes": [
                {"id": n.id, "employee_id": n.employee_id, "note": n.note, "created_at": str(n.created_at)}
                for n in case_notes
            ],
        }
    finally:
        db.close()


@router.post("/cases/{case_id}/replay")
def replay_case(case_id: int):
    db = SessionLocal()
    try:
        case = db.query(Case).filter_by(id=case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        import json
        inputs = json.loads(case.inputs_json or "{}")
        artifacts = json.loads(case.artifacts_json or "{}")
        # idempotency_key=None means replay always creates a brand-new case
        # (and a brand-new case note) with no durable link back to the
        # original case (see P011).
        result = run_workflow(
            inputs=inputs,
            idempotency_key=None,
        )
        return result
    finally:
        db.close()
