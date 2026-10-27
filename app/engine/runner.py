import json
import logging
import time
from datetime import datetime, timezone


from sqlalchemy.exc import IntegrityError


from app.engine.context import ExecutionContext
from app.engine.steps import STEPS
from app.storage.database import SessionLocal
from app.storage.models import Case, Step
from app.tools.hris import post_case_note_to_hris


logger = logging.getLogger(__name__)

#catch when someone inputs an existing idempotency key but with mismatched emp id and/or desc
class IdempotencyConflict(Exception):
    """The idempotency key was already used with different inputs"""

def _check_same_inputs(case: Case, inputs: dict) -> None:
    if json.loads(case.inputs_json or "{}") != inputs:
        raise IdempotencyConflict("Idempotency key was already used with different inputs")

#flag sensitive topics only for human review - should confirm and expand with HR and Legal before production 
HUMAN_ONLY_TOPICS = {"harassment": ("harass",)}

def _human_only_topic(text: str) -> str | None:
    """Return the topic name if this case must go to a person, otherwise None."""
    lowered = text.lower()
    for topic, fragments in HUMAN_ONLY_TOPICS.items():
        if any(fragment in lowered for fragment in fragments):
            return topic
    return None

#catch failed steps 
class WorkflowFailed(Exception):
    """A failure occured. Case saved with status "failed" and the error in cases table"""

    def __init__(self, case_id: int, step_name: str | None, error_type: str):
        super().__init__(f"case {case_id} failed at step {step_name}: {error_type}")
        self.case_id = case_id
        self.step_name = step_name
        self.error_type = error_type


def _mark_failed(db, case_id: int, step_name: str | None, exc: Exception) -> None:
    """Record the failure on the case: step and error type only."""
    try:
        db.rollback()
        case = db.get(Case, case_id)
        case.status = "failed"
        case.error = f"{step_name}: {type(exc).__name__}"
        db.commit()
    except Exception:
        logger.exception("Could not record failure for case %s", case_id)



def run_workflow(
    inputs: dict,
    idempotency_key: str | None = None,
    replay_of: int | None = None,
    write_case_note: bool = True,
) -> dict:
    db = SessionLocal()
    try:
        #only find the first db record if the idempotency key is not null to fix bug of finding the last previous null when a key is not given
        existing = None
        if idempotency_key is not None:
            existing = db.query(Case).filter_by(idempotency_key=idempotency_key).first()
        #use new check to see if an existing idempotency key has the same inputs as the db
        if existing is not None:
            _check_same_inputs(existing, inputs)
        if existing and existing.status in ("completed", "needs_human_review"):
            return {
                "case_id": existing.id,
                "status": existing.status,
                "outputs": json.loads(existing.outputs_json or "{}"),
            }
        if existing and existing.status == "running":
            return {
                "case_id": existing.id,
                "status": existing.status,
                "outputs": json.loads(existing.outputs_json or "{}"),
            }
        #previously failed case, resume. eliminates potential duplicates if previous failed case is rerun twice 
        if existing and existing.status == "failed": 
            claimed = (
                db.query(Case)
                .filter(Case.id == existing.id, Case.status == "failed")
                .update({"status": "running", "error": None}) 
            )
            db.commit()
            if not claimed:
                db.refresh(existing)
                return {
                    "case_id": existing.id,
                    "status": existing.status,
                    "outputs": json.loads(existing.outputs_json or "{}"),
                }
            case = existing
        else:
            case = Case(
                status="running",
                idempotency_key=idempotency_key,
                inputs_json=json.dumps(inputs),
                artifacts_json=json.dumps({"prompt_version": "v1"}),
                replay_of=replay_of
            )
            db.add(case)
            #try except added to work with new WAL configuration in db
            try:
                db.commit()
            except IntegrityError:
                # Another request with the same key got there first. Return the winner's case
                db.rollback()
                winner = db.query(Case).filter_by(idempotency_key=idempotency_key).first()
                if winner is None:
                    #flag to catch other issue (something is wrong if there is no matching key)
                    raise
                # new check if case with previous idempotency key is used, check all inputs match
                _check_same_inputs(winner, inputs)
                return {
                    "case_id": winner.id,
                    "status": winner.status,
                    "outputs": json.loads(winner.outputs_json or "{}"),
                }
            db.refresh(case)

        artifacts = {"prompt_version": "v1", "model_name": "stub"}
        #remove human reviewed only topics 
        case_id = case.id
        topic = _human_only_topic(inputs.get("case_transcript", ""))
        if topic:
            try:
                if write_case_note:
                    post_case_note_to_hris(
                        case_id=case_id,
                        employee_id=inputs["employee_id"],
                        note=(
                            f"Case {case_id} routed to HR for human review due to sensitive topic. "
                            "No automated draft was generated."
                        ),
                    )
            except Exception as e:
                _mark_failed(db, case_id, "route_to_human", e)
                raise WorkflowFailed(case_id, "route_to_human", type(e).__name__) from e
            case.status = "needs_human_review"
            case.error = f"human review: {topic}"  # topic name only, never the text
            db.commit()
            return {"case_id": case_id, "status": case.status, "outputs": {}, "error": case.error}
        ctx = ExecutionContext(
            case_id=case.id,
            inputs=inputs,
            artifacts=artifacts,
            options={"write_case_note": write_case_note}
        )

        for step_name, step_fn in STEPS:
            step_start = time.time()
            step_record = Step(
                case_id=case.id,
                name=step_name,
                status="running",
                started_at=datetime.now(timezone.utc),
                attempts=1,
            )
            db.add(step_record)
            db.commit()

            try:
                output = step_fn(ctx)
                ctx.step_outputs[step_name] = output
                step_record.status = "completed"
                step_record.output_json = json.dumps(output) if not isinstance(output, (str, int, float, bool)) else json.dumps({"value": output})
            except Exception as e:
                #log the failed step's error type and mark the step as failed
                logger.error("Step %s failed for case %s: %s", step_name, case.id, type(e).__name__)
                step_record.status = "failed"
                step_record.error = f"{type(e).__name__}: {str(e)[:200]}"
                db.commit()
                _mark_failed(db, case.id, step_name, e)
                raise WorkflowFailed(case.id, step_name, type(e).__name__) from e

            step_record.finished_at = datetime.now(timezone.utc)
            step_record.attempts = getattr(step_record, "attempts", 1)
            db.commit()

            elapsed = time.time() - step_start
            logger.info(f"Step {step_name} completed in {elapsed:.2f}s")

        final_output = ctx.step_outputs.get("generate_structured_response", {})
        case.status = "completed"
        case.outputs_json = json.dumps(final_output)
        db.commit()

        return {
            "case_id": case.id,
            "status": case.status,
            "outputs": final_output,
        }
    finally:
        db.close()
