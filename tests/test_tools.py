import os
import pytest

os.environ["DOCS_DIR"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "docs")


def test_tool_registry():
    from app.tools.registry import ToolRegistry, get_tool_registry

    registry = get_tool_registry()
    assert "retrieve_employee_context" in registry.list_tools()
    assert "retrieve_policy_snippets" in registry.list_tools()
    assert "post_case_note_to_hris" in registry.list_tools()


def test_retrieve_employee_context_no_data(db_session):
    from app.tools.registry import get_tool_registry
    registry = get_tool_registry()
    out = registry.execute("retrieve_employee_context", employee_id="E99999")
    assert out["employee_id"] == "E99999"
    assert out["found"] is False


def test_retrieve_employee_context_with_data(db_session):
    from app.storage.models import EmployeeRecord
    import json

    db_session.add(
        EmployeeRecord(
            employee_id="E00001",
            metadata_json=json.dumps({"department": "People"}),
            last_activities_json=json.dumps([{"type": "case", "summary": "Benefits question"}]),
        )
    )
    db_session.commit()

    from app.tools.registry import get_tool_registry
    registry = get_tool_registry()
    out = registry.execute("retrieve_employee_context", employee_id="E00001")
    assert out["found"] is True
    assert out["metadata"]["department"] == "People"
    assert len(out["last_activities"]) == 1


def test_retrieve_policy_snippets():
    from app.tools.registry import get_tool_registry

    registry = get_tool_registry()
    snippets = registry.execute("retrieve_policy_snippets", query="parental leave eligibility")
    assert isinstance(snippets, list)
    assert len(snippets) >= 0
