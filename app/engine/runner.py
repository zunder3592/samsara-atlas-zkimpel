import json
import logging
import time
from datetime import datetime, timezone

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError


from app.engine.context import ExecutionContext
from app.engine.steps import STEPS
from app.storage.database import SessionLocal
from app.storage.models import Case, Step


logger = logging.getLogger(__name__)
#catch when someone inputs an existing idempotency key but with mismatched emp id and/or desc
class IdempotencyConflict(Exception):
    """The idempotency key was already used with different inputs"""


def _check_same_inputs(case: Case, inputs: dict) -> None:
    if json.loads(case.inputs_json or "{}") != inputs:
        raise IdempotencyConflict("Idempotency key was already used with different inputs")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((TimeoutError, ValidationError, ValueError)),
)
def run_workflow(
    inputs: dict,
    idempotency_key: str | None = None,
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
        if existing and existing.status == "completed":
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
        if existing and existing.status == "failed":
            case = existing
            case.status = "running"
            db.commit()
        else:
            case = Case(
                status="running",
                idempotency_key=idempotency_key,
                inputs_json=json.dumps(inputs),
                artifacts_json=json.dumps({"prompt_version": "v1"}),
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
        ctx = ExecutionContext(
            case_id=case.id,
            inputs=inputs,
            artifacts=artifacts,
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
                logger.exception("Step failed")
                step_record.status = "failed"
                step_record.error = str(e)
                db.commit()
                raise

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
