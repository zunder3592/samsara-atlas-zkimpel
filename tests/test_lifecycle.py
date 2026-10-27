import json
import pytest
from sqlalchemy.exc import IntegrityError
import concurrent.futures
from fastapi.testclient import TestClient

from app.engine.runner import run_workflow, IdempotencyConflict, WorkflowFailed
import app.engine.runner as runner_module
from app.storage.database import SessionLocal
from app.storage.models import EmployeeRecord
from app.storage.models import Case, CaseNote, EmployeeRecord, Step
import app.engine.steps as steps_module
from app.providers.base import CompletionResponse


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

@pytest.fixture
def client(db_session):
    from app.main import app

    return TestClient(app)

def _inputs(text="Asked how PTO carryover works.", tone="empathetic"):
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

def _get_case(case_id):
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        db.expunge(case)
        return case
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


def test_same_key_different_inputs_is_a_conflict(seeded):
    key = "lifecycle-conflict-key"
    run_workflow(_inputs("First description."), idempotency_key=key)
    with pytest.raises(IdempotencyConflict):
        run_workflow(_inputs("A different description."), idempotency_key=key)


def test_failed_step_marks_case_failed(seeded, monkeypatch):
    key = "lifecycle-fail-key"

    def boom(ctx):
        raise RuntimeError("secret case text that must not be stored")

    monkeypatch.setattr(runner_module, "STEPS", [("explode", boom)]) 
    with pytest.raises(WorkflowFailed) as info:
        run_workflow(_inputs(), idempotency_key=key)

    case = _get_case(info.value.case_id)
    assert case.status == "failed"
    assert case.error == "explode: RuntimeError"
    assert "secret" not in case.error
    assert _count(Case, idempotency_key=key) == 1

def test_api_failure_returns_case_id_and_no_message_text(client, seeded, monkeypatch):
    def boom(ctx):
        raise RuntimeError("secret case text that must not be returned")

    monkeypatch.setattr(runner_module, "STEPS", [("explode", boom)])
    resp = client.post("/cases", json={"inputs": _inputs(), "idempotency_key": "lifecycle-api-fail"})
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail["step"] == "explode"
    assert detail["error"] == "RuntimeError"
    assert "secret" not in resp.text

    stored = client.get(f"/cases/{detail['case_id']}").json()
    assert stored["case"]["status"] == "failed"



#retry tests
SUMMARY_JSON = '{"summary": "A short summary.", "action_items": ["Check policy"], "next_steps": ["Reply"]}'
RESPONSE_JSON = '{"subject": "Your request", "body": "Here is what we found.", "tone": "empathetic", "cited_snippets": ["Policy excerpt"]}'


class FakeProvider:
    """Stands in for the AI model. Returns the given replies in order,
    or raises `error` on every call."""

    def __init__(self, replies=(), error=None):
        self.replies = list(replies)
        self.error = error
        self.calls = 0

    def complete(self, prompt, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return CompletionResponse(text=self.replies.pop(0), raw=None)


def test_bad_model_output_is_retried_without_rerunning_earlier_steps(seeded, monkeypatch):
    provider = FakeProvider(replies=["this is not json", SUMMARY_JSON, RESPONSE_JSON])
    monkeypatch.setattr(steps_module, "get_provider", lambda: provider)

    result = run_workflow(_inputs(), idempotency_key="lifecycle-retry-recovers")

    assert result["status"] == "completed"
    assert provider.calls == 3  # summarize twice (first reply was bad), draft once
    assert _count(Step, case_id=result["case_id"]) == 5  # earlier steps were not re-run


def test_bad_model_output_every_time_fails_after_two_attempts(seeded, monkeypatch):
    provider = FakeProvider(replies=["not json"] * 5)
    monkeypatch.setattr(steps_module, "get_provider", lambda: provider)

    with pytest.raises(WorkflowFailed) as info:
        run_workflow(_inputs(), idempotency_key="lifecycle-retry-gives-up")

    assert info.value.error_type == "JSONDecodeError"
    assert provider.calls == 2


def test_connection_failure_reports_the_real_error(seeded, monkeypatch):
    provider = FakeProvider(error=ConnectionError("model server down"))
    monkeypatch.setattr(steps_module, "get_provider", lambda: provider)

    with pytest.raises(WorkflowFailed) as info:
        run_workflow(_inputs(), idempotency_key="lifecycle-connection-down")

    assert info.value.error_type == "ConnectionError"
    assert provider.calls == 3


#one email per case

def test_case_note_tool_writes_at_most_one_note_per_case(seeded):
    from app.tools.hris import post_case_note_to_hris

    case = run_workflow(_inputs())  # the workflow already wrote one note
    assert _count(CaseNote, case_id=case["case_id"]) == 1

    post_case_note_to_hris(case_id=case["case_id"], employee_id="E10234", note="second try")
    assert _count(CaseNote, case_id=case["case_id"]) == 1


# replay case button 


def test_replay_is_linked_and_writes_no_case_note_by_default(client, seeded):
    original = client.post(
        "/cases", json={"inputs": _inputs(), "idempotency_key": "lifecycle-replay-orig"}
    ).json()

    replay = client.post(f"/cases/{original['case_id']}/replay").json()
    assert replay["case_id"] != original["case_id"]
    assert _get_case(replay["case_id"]).replay_of == original["case_id"]
    assert _count(CaseNote, case_id=original["case_id"]) == 1
    assert _count(CaseNote, case_id=replay["case_id"]) == 0

    with_note = client.post(f"/cases/{original['case_id']}/replay?write_case_note=true").json()
    assert _count(CaseNote, case_id=with_note["case_id"]) == 1



#limit emp data going to model

class RecordingProvider:
    """A fake model that remembers every prompt it was sent."""

    def __init__(self):
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return CompletionResponse(
                text=json.dumps({"summary": "s", "action_items": [], "next_steps": []})
            )
        return CompletionResponse(
            text=json.dumps(
                {"subject": "Subject", "body": "Body", "tone": "empathetic", "cited_snippets": []}
            )
        )


def test_model_prompts_exclude_employee_id_and_extra_record_fields(db_session, monkeypatch):
    db = SessionLocal()
    try:
        db.add(
            EmployeeRecord(
                employee_id="E77777",
                metadata_json=json.dumps(
                    {
                        "manager": "Secret Manager",
                        "location": "Remote - US Zone 9",
                        "tenure_years": 7.5,
                        "employment_status": "active",
                    }
                ),
                last_activities_json=json.dumps([{"summary": "Secret past case"}]),
            )
        )
        db.commit()
    finally:
        db.close()

    provider = RecordingProvider()
    monkeypatch.setattr(steps_module, "get_provider", lambda: provider)

    inputs = {"employee_id": "E77777", "case_transcript": "Asked about leave.", "tone": "empathetic"}
    result = run_workflow(inputs)
    assert result["status"] == "completed"

    combined = " ".join(provider.prompts)
    assert len(provider.prompts) == 2  # one per AI step
    assert "E77777" not in combined
    assert "Secret Manager" not in combined
    assert "Secret past case" not in combined
    assert "Remote - US Zone 9" in combined  # allowed fields still get through

#sensitive topic rerouting 
# --- sensitive topics go to a person ---------------------------------------


def test_harassment_case_skips_the_model_and_writes_a_routing_note(seeded, monkeypatch):
    provider = RecordingProvider()
    monkeypatch.setattr(steps_module, "get_provider", lambda: provider)

    result = run_workflow(_inputs("I want to report harassment by a coworker."))
    case_id = result["case_id"]

    assert result["status"] == "needs_human_review"
    assert provider.prompts == []  # the model was never called
    assert _count(Step, case_id=case_id) == 0
    assert _get_case(case_id).error == "human review: harassment"

    db = SessionLocal()
    try:
        note = db.query(CaseNote).filter_by(case_id=case_id).one().note
    finally:
        db.close()
    assert note == (
        f"Case {case_id} routed to HR for human review due to sensitive topic. "
        "No automated draft was generated."
    )
    assert "coworker" not in note  # the note never contains the case text


def test_human_review_case_is_returned_again_for_the_same_key(seeded):
    key = "lifecycle-human-review-key"
    text = "I am being harassed at work."
    first = run_workflow(_inputs(text), idempotency_key=key)
    second = run_workflow(_inputs(text), idempotency_key=key)
    assert first["status"] == "needs_human_review"
    assert second["case_id"] == first["case_id"]
    assert second["status"] == "needs_human_review"
    assert _count(Case, idempotency_key=key) == 1
    assert _count(CaseNote, case_id=first["case_id"]) == 1
