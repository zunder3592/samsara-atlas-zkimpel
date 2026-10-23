import json
import pytest
from sqlalchemy.exc import IntegrityError
import concurrent.futures

from app.engine.runner import run_workflow
from app.storage.database import SessionLocal
from app.storage.models import EmployeeRecord
from app.storage.models import Case, CaseNote, EmployeeRecord

@pytest.fixture
def seeded(db_session):
    db = SessionLocal()
    try:
        if not db.query(EmployeeRecord).filter_by(employee_id="E10234").first():
            db.add(
                EmployeeRecord(
                    employee_id="E10234",
                    metadata_json=json.dumps({"department": "Field Operations"}),
                    last_activities_json=json.dumps([]),
                )
            )
            db.commit()
    finally:
        db.close()


def _inputs(text, tone="empathetic"):
    return {"employee_id": "E10234", "case_transcript": text, "tone": tone}


def test_keyless_requests_create_separate_cases(seeded):
    a = run_workflow(_inputs("Question about PTO carryover."))
    b = run_workflow(_inputs("Leave of absence for a family medical situation.", "formal"))
    assert a["case_id"] != b["case_id"]


def test_database_enforces_unique_key_but_allows_many_keyless(db_session):
    db = SessionLocal()
    try:
        db.add(Case(status="x", idempotency_key="lifecycle-dup-key"))
        db.commit()
        db.add(Case(status="y", idempotency_key="lifecycle-dup-key"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Case(status="x", idempotency_key=None))
        db.add(Case(status="y", idempotency_key=None))
        db.commit()  # two blank keys are fine
    finally:
        db.close()


def _count(model, **filters):
    db = SessionLocal()
    try:
        return db.query(model).filter_by(**filters).count()
    finally:
        db.close()


def test_concurrent_same_key_creates_one_case(seeded):
    key = "lifecycle-concurrent-key"
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run_workflow, _inputs("Same request."), idempotency_key=key) for _ in range(8)]
        results = [f.result() for f in futures]  # raises if any call errored
    assert len({r["case_id"] for r in results}) == 1
    assert _count(Case, idempotency_key=key) == 1
    assert _count(CaseNote, case_id=results[0]["case_id"]) == 1