import os

import pytest
from fastapi.testclient import TestClient

os.environ["DOCS_DIR"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")


@pytest.fixture
def client(db_session):
    from app.main import app
    return TestClient(app)


@pytest.fixture
def seeded_db(client, db_session):
    from app.storage.models import EmployeeRecord
    import json

    existing = db_session.query(EmployeeRecord).filter_by(employee_id="E10234").first()
    if not existing:
        db_session.add(
            EmployeeRecord(
                employee_id="E10234",
                metadata_json=json.dumps({"department": "Field Operations"}),
                last_activities_json=json.dumps([]),
            )
        )
        db_session.commit()


def test_post_cases_happy_path(client, seeded_db):
    resp = client.post(
        "/cases",
        json={
            "inputs": {
                "employee_id": "E10234",
                "case_transcript": "Asked how PTO carryover works going into next year.",
                "tone": "empathetic",
            },
            "idempotency_key": "api-test-key",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "case_id" in data
    assert data["status"] == "completed"
    assert "subject" in data["outputs"]


def test_get_case(client, seeded_db):
    create_resp = client.post(
        "/cases",
        json={
            "inputs": {
                "employee_id": "E10234",
                "case_transcript": "Test case.",
                "tone": "direct",
            },
            "idempotency_key": "get-test-key",
        },
    )
    case_id = create_resp.json()["case_id"]

    get_resp = client.get(f"/cases/{case_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "case" in data
    assert "steps" in data
    assert "case_notes" in data
