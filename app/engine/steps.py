import json
import logging
import os
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.providers.factory import get_provider
from app.tools.registry import get_tool_registry
from app.schemas import StructuredResponse, ExtractActionsOutput

logger = logging.getLogger(__name__)


def _load_prompt(name: str) -> str:
    """Load prompt from file - no content hash; replay uses current file (prompt drift, see P010)."""
    path = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
    return path.read_text()


def _parse_json_from_text(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        lines = text.split("\n")
        in_block = False
        start_idx = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                if not in_block:
                    in_block = True
                    start_idx = i + 1 if "json" in line else i
                else:
                    text = "\n".join(lines[start_idx:i])
                    break
        else:
            text = "\n".join(lines[start_idx:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def step_retry(exc):
    """Retry on transient errors - but too broad at the workflow level (see P006/P007)."""
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError, OSError)),
    reraise=True # surfaces true error
)
def _retryable_llm_call(prompt: str, **kwargs):
    provider = get_provider()
    resp = provider.complete(prompt, **kwargs)
    text = resp.text
    raw = resp.raw
    if raw and isinstance(raw, dict):
        choices = raw.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            text = msg.get("content", text)
    return text

@retry(
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(json.JSONDecodeError),
    reraise=True,
)
def _ask_for_json(prompt: str, **kwargs) -> dict:
    """Ask the model and read its reply as JSON. If the reply isn't valid
    JSON, ask again once. Only this step is retried, so a retry never
    re-runs earlier steps."""
    return _parse_json_from_text(_retryable_llm_call(prompt, **kwargs))

def retrieve_employee_context_step(ctx):
    registry = get_tool_registry()
    out = registry.execute("retrieve_employee_context", employee_id=ctx.inputs["employee_id"])
    return out


def retrieve_policy_snippets_step(ctx):
    registry = get_tool_registry()
    out = registry.execute(
        "retrieve_policy_snippets",
        query=ctx.inputs["case_transcript"],
    )
    return out


def _normalize_summary(data: dict) -> dict:
    """Normalize LLM output keys (action_items vs actionItems, etc)."""
    return {
        "summary": data.get("summary", data.get("Summary", "")),
        "action_items": data.get("action_items", data.get("actionItems", [])),
        "next_steps": data.get("next_steps", data.get("nextSteps", [])),
    }


def summarize_and_extract_actions_step(ctx):
    prompt_tpl = _load_prompt("summarize")
    prompt = prompt_tpl.format(
        employee_id=ctx.inputs["employee_id"],
        case_transcript=ctx.inputs["case_transcript"],
    )
    data = _ask_for_json(prompt)
    # ExtractActionsOutput is defined in schemas.py but never used to validate `data` here (see P013).
    return _normalize_summary(data)


def generate_structured_response_step(ctx):
    employee = ctx.step_outputs.get("retrieve_employee_context", {})
    snippets = ctx.step_outputs.get("retrieve_policy_snippets", [])
    actions = ctx.step_outputs.get("summarize_and_extract_actions", {})
    actions_str = json.dumps(actions, indent=2) if isinstance(actions, dict) else str(actions)
    employee_str = json.dumps(employee, indent=2) if isinstance(employee, dict) else str(employee)
    snippets_str = "\n\n---\n\n".join(f"[{i+1}] {s[:600]}" for i, s in enumerate(snippets[:5])) if snippets else "(none retrieved)"

    prompt_tpl = _load_prompt("generate_response")
    prompt = prompt_tpl.format(
        employee_id=ctx.inputs["employee_id"],
        employee_context=employee_str,
        policy_snippets=snippets_str,
        actions=actions_str,
        tone=ctx.inputs["tone"],
    )
    data = _ask_for_json(prompt, tone=ctx.inputs["tone"])
    normalized = {
        "subject": data.get("subject", data.get("Subject", "")),
        "body": data.get("body", data.get("Body", "")),
        "tone": data.get("tone", data.get("Tone", ctx.inputs["tone"])),
        "cited_snippets": data.get("cited_snippets", data.get("citedSnippets", [])),
    }
    return StructuredResponse(**normalized).model_dump()


def post_case_note_to_hris_step(ctx):
    if not ctx.options.get("write_case_note", True):
        return {"skipped": True, "reason": "case note disabled for this run"}
    response = ctx.step_outputs.get("generate_structured_response", {})
    note = f"Response drafted: {response.get('subject', '')} - {response.get('body', '')[:200]}"
    registry = get_tool_registry()
    out = registry.execute(
        "post_case_note_to_hris",
        case_id=ctx.case_id,
        employee_id=ctx.inputs["employee_id"],
        note=note,
    )
    return out


STEPS = [
    ("retrieve_employee_context", retrieve_employee_context_step),
    ("retrieve_policy_snippets", retrieve_policy_snippets_step),
    ("summarize_and_extract_actions", summarize_and_extract_actions_step),
    ("generate_structured_response", generate_structured_response_step),
    ("post_case_note_to_hris", post_case_note_to_hris_step),
]
