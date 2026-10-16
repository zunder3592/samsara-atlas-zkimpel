import os

import pytest

os.environ["DOCS_DIR"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")


@pytest.fixture
def seeded_db(db_session):
    from app.storage.models import EmployeeRecord
    import json

    existing = db_session.query(EmployeeRecord).filter_by(employee_id="E10234").first()
    if not existing:
        db_session.add(
            EmployeeRecord(
                employee_id="E10234",
                metadata_json=json.dumps({"department": "Field Operations", "tenure_years": 2.4}),
                last_activities_json=json.dumps([{"type": "case", "summary": "PTO question"}]),
            )
        )
        db_session.commit()


def test_workflow_happy_path(seeded_db):
    from app.engine.runner import run_workflow

    inputs = {
        "employee_id": "E10234",
        "case_transcript": "Asked how PTO carryover works. Has about 30 unused hours.",
        "tone": "empathetic",
    }
    result = run_workflow(inputs=inputs, idempotency_key="test-key-123")
    assert result["status"] == "completed"
    assert "case_id" in result
    assert "outputs" in result
    assert "subject" in result["outputs"]
    assert "body" in result["outputs"]
    assert "tone" in result["outputs"]
    assert "cited_snippets" in result["outputs"]
