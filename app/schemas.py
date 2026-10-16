from typing import Literal

from pydantic import BaseModel


class CaseInputs(BaseModel):
    employee_id: str
    case_transcript: str
    tone: Literal["empathetic", "direct", "formal"]


class StructuredResponse(BaseModel):
    subject: str
    body: str
    tone: Literal["empathetic", "direct", "formal"]
    cited_snippets: list[str]


class ExtractActionsOutput(BaseModel):
    """Schema for summarize_and_extract_actions - NOT validated in engine (intentional flaw, see P013)."""
    summary: str
    action_items: list[str]
    next_steps: list[str]
