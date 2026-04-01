"""Tests for orchestration/tools."""

from __future__ import annotations

import pytest

from orchestration.tools.definitions import get_tool_definitions
from orchestration.tools.handlers import (
    ToolResult,
    handle_generate_action_cards,
    handle_generate_decision_quiz,
    handle_tool_call,
    handle_update_kanban,
)
from orchestration.tools.retry import build_retry_prompt
from orchestration.tools.validation import validate_tool_call


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def base_state() -> dict:
    """A minimal session state suitable for tool handler tests."""

    return {
        "session_id": "sess_test",
        "moderator_role_id": "RG-FAC",
        "all_role_ids": ["RG-FAC", "RG-CRIT", "RE-ARCH", "RR-LEAD"],
        "kanban": {
            "tasks": [
                {"task_id": "Q-01", "title": "Q-01 text", "status": "TO_DISCUSS", "notes": ""},
                {"task_id": "Q-02", "title": "Q-02 text", "status": "TO_DISCUSS", "notes": ""},
            ]
        },
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
    }


# ---------------------------------------------------------------------------
# TASK-09 AC: get_tool_definitions returns exactly 3 tools matching §5.1
# ---------------------------------------------------------------------------


def test_get_tool_definitions_returns_three():
    tools = get_tool_definitions()
    assert len(tools) == 3
    names = {t.name for t in tools}
    assert names == {"generate_action_cards", "generate_decision_quiz", "update_kanban"}


def test_tool_definitions_have_required_schemas():
    tools = {t.name: t for t in get_tool_definitions()}

    ac = tools["generate_action_cards"]
    assert "cards" in ac.parameters["properties"]
    required_in_card = ac.parameters["properties"]["cards"]["items"]["required"]
    assert set(required_in_card) >= {"target_role_id", "prompt_text", "context_note"}

    dq = tools["generate_decision_quiz"]
    assert set(dq.parameters["required"]) >= {"decision_title", "options", "context_summary"}

    uk = tools["update_kanban"]
    assert "updates" in uk.parameters["required"]


# ---------------------------------------------------------------------------
# handle_generate_action_cards
# ---------------------------------------------------------------------------


def test_handle_generate_action_cards_creates_cards(base_state):
    args = {
        "cards": [
            {
                "target_role_id": "RG-CRIT",
                "prompt_text": "Analyse domain boundaries",
                "context_note": "Need critic perspective",
                "linked_question_ids": ["Q-01"],
            }
        ]
    }
    result = handle_generate_action_cards(args, base_state)

    assert result.success is True
    assert len(base_state["pending_action_cards"]) == 1
    card = base_state["pending_action_cards"][0]
    assert card["target_role_id"] == "RG-CRIT"
    assert card["status"] == "PENDING"
    assert card["linked_question_ids"] == ["Q-01"]


def test_handle_generate_action_cards_returns_ws_event(base_state):
    args = {
        "cards": [
            {
                "target_role_id": "RG-CRIT",
                "prompt_text": "Analyse",
                "context_note": "Note",
            }
        ]
    }
    result = handle_generate_action_cards(args, base_state)
    assert len(result.ws_events) == 1
    assert result.ws_events[0]["event"] == "action_cards_created"
    assert "cards" in result.ws_events[0]["data"]


def test_handle_action_cards_multiple(base_state):
    args = {
        "cards": [
            {"target_role_id": "RG-CRIT", "prompt_text": "P1", "context_note": "N1"},
            {"target_role_id": "RE-ARCH", "prompt_text": "P2", "context_note": "N2"},
        ]
    }
    result = handle_generate_action_cards(args, base_state)
    assert result.success is True
    assert len(base_state["pending_action_cards"]) == 2
    assert "Created 2 action card(s)" in result.message


# ---------------------------------------------------------------------------
# handle_generate_decision_quiz
# ---------------------------------------------------------------------------


def test_handle_generate_decision_quiz_creates_quiz(base_state):
    args = {
        "decision_title": "Which domain owns auth?",
        "options": ["Governance", "Audit", "Both"],
        "context_summary": "Agents disagree on auth ownership.",
        "linked_question_ids": ["Q-01"],
    }
    result = handle_generate_decision_quiz(args, base_state)

    assert result.success is True
    assert len(base_state["pending_quizzes"]) == 1
    quiz = base_state["pending_quizzes"][0]
    assert quiz["decision_title"] == "Which domain owns auth?"
    assert quiz["options"] == ["Governance", "Audit", "Both"]
    assert quiz["resolved"] is False


def test_handle_generate_decision_quiz_returns_ws_event(base_state):
    args = {
        "decision_title": "Q",
        "options": ["A", "B"],
        "context_summary": "Context",
    }
    result = handle_generate_decision_quiz(args, base_state)
    assert len(result.ws_events) == 1
    assert result.ws_events[0]["event"] == "decision_quiz_created"


# ---------------------------------------------------------------------------
# handle_update_kanban
# ---------------------------------------------------------------------------


def test_handle_update_kanban_updates_status(base_state):
    args = {
        "updates": [{"question_id": "Q-01", "new_status": "AGENT_DELIBERATION", "notes": "Started"}]
    }
    result = handle_update_kanban(args, base_state)

    assert result.success is True
    tasks = {t["task_id"]: t for t in base_state["kanban"]["tasks"]}
    assert tasks["Q-01"]["status"] == "AGENT_DELIBERATION"
    assert tasks["Q-01"]["notes"] == "Started"
    assert tasks["Q-02"]["status"] == "TO_DISCUSS"  # unchanged


def test_handle_update_kanban_returns_ws_event(base_state):
    args = {"updates": [{"question_id": "Q-01", "new_status": "RESOLVED"}]}
    result = handle_update_kanban(args, base_state)
    assert len(result.ws_events) == 1
    assert result.ws_events[0]["event"] == "kanban_updated"


def test_handle_update_kanban_unknown_id_silently_skips(base_state):
    """Unknown question_id is a no-op in the handler (validation catches it earlier)."""

    args = {"updates": [{"question_id": "Q-99", "new_status": "RESOLVED"}]}
    result = handle_update_kanban(args, base_state)
    assert result.success is True
    assert "0 kanban task(s)" in result.message


# ---------------------------------------------------------------------------
# handle_tool_call dispatcher
# ---------------------------------------------------------------------------


def test_handle_tool_call_unknown_returns_failure(base_state):
    result = handle_tool_call("nonexistent_tool", {}, base_state)
    assert result.success is False


def test_handle_tool_call_dispatches_correctly(base_state):
    args = {
        "cards": [
            {"target_role_id": "RG-CRIT", "prompt_text": "P", "context_note": "N"}
        ]
    }
    result = handle_tool_call("generate_action_cards", args, base_state)
    assert result.success is True
    assert len(base_state["pending_action_cards"]) == 1


# ---------------------------------------------------------------------------
# validate_tool_call
# ---------------------------------------------------------------------------


def test_validate_unknown_tool(base_state):
    errors = validate_tool_call("bad_tool", {}, base_state)
    assert errors
    assert any("Unknown tool" in e for e in errors)


def test_validate_action_cards_missing_required(base_state):
    errors = validate_tool_call(
        "generate_action_cards",
        {"cards": [{"target_role_id": "RG-CRIT"}]},  # missing prompt_text, context_note
        base_state,
    )
    assert any("prompt_text" in e for e in errors)
    assert any("context_note" in e for e in errors)


def test_validate_action_cards_missing_cards_key(base_state):
    errors = validate_tool_call("generate_action_cards", {}, base_state)
    assert errors


def test_validate_action_cards_rejects_moderator_target(base_state):
    args = {
        "cards": [
            {
                "target_role_id": "RG-FAC",  # the moderator
                "prompt_text": "Prompt",
                "context_note": "Note",
            }
        ]
    }
    errors = validate_tool_call("generate_action_cards", args, base_state)
    assert any("moderator" in e.lower() for e in errors)


def test_validate_action_cards_rejects_unknown_role(base_state):
    args = {
        "cards": [
            {
                "target_role_id": "XX-UNKNOWN",
                "prompt_text": "Prompt",
                "context_note": "Note",
            }
        ]
    }
    errors = validate_tool_call("generate_action_cards", args, base_state)
    assert any("not a valid session role" in e for e in errors)


def test_validate_decision_quiz_missing_fields(base_state):
    errors = validate_tool_call(
        "generate_decision_quiz",
        {"decision_title": "Q"},  # missing options and context_summary
        base_state,
    )
    assert any("options" in e for e in errors)
    assert any("context_summary" in e for e in errors)


def test_validate_update_kanban_missing_updates(base_state):
    errors = validate_tool_call("update_kanban", {}, base_state)
    assert errors


def test_validate_update_kanban_unknown_question_id(base_state):
    args = {"updates": [{"question_id": "Q-99", "new_status": "RESOLVED"}]}
    errors = validate_tool_call("update_kanban", args, base_state)
    assert any("Q-99" in e for e in errors)


def test_validate_update_kanban_invalid_status(base_state):
    args = {"updates": [{"question_id": "Q-01", "new_status": "BOGUS_STATUS"}]}
    errors = validate_tool_call("update_kanban", args, base_state)
    assert any("invalid status" in e.lower() for e in errors)


def test_validate_valid_action_cards_passes(base_state):
    args = {
        "cards": [
            {
                "target_role_id": "RG-CRIT",
                "prompt_text": "Analyse boundaries",
                "context_note": "Need critic perspective",
                "linked_question_ids": ["Q-01"],
            }
        ]
    }
    errors = validate_tool_call("generate_action_cards", args, base_state)
    assert errors == []


def test_validate_valid_update_kanban_passes(base_state):
    args = {"updates": [{"question_id": "Q-01", "new_status": "RESOLVED", "notes": "Done"}]}
    errors = validate_tool_call("update_kanban", args, base_state)
    assert errors == []


# ---------------------------------------------------------------------------
# build_retry_prompt
# ---------------------------------------------------------------------------


def test_build_retry_prompt_includes_tool_name():
    prompt = build_retry_prompt("generate_action_cards", {"cards": []}, ["Missing target_role_id"])
    assert "generate_action_cards" in prompt


def test_build_retry_prompt_includes_arguments():
    prompt = build_retry_prompt("update_kanban", {"updates": [{"question_id": "Q-99"}]}, ["Q-99 not found"])
    assert "Q-99" in prompt


def test_build_retry_prompt_includes_errors():
    errors = ["Error one", "Error two"]
    prompt = build_retry_prompt("update_kanban", {}, errors)
    assert "Error one" in prompt
    assert "Error two" in prompt


# ---------------------------------------------------------------------------
# Handlers do NOT broadcast — events are returned, not sent
# ---------------------------------------------------------------------------


def test_handlers_return_events_not_broadcast(base_state):
    """Confirm handlers return ws_events list rather than calling any WebSocket."""

    args = {
        "cards": [
            {"target_role_id": "RG-CRIT", "prompt_text": "P", "context_note": "N"}
        ]
    }
    result = handle_tool_call("generate_action_cards", args, base_state)
    assert isinstance(result, ToolResult)
    assert isinstance(result.ws_events, list)
    # If handlers called manager.broadcast, they'd need a WebSocket mock — they don't.
