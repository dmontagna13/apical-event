"""Moderator tool call handlers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import uuid4

from core.schemas import ActionCard, DecisionQuiz
from orchestration.tools.validation import ToolValidationError


@dataclass
class ToolResult:
    """Result returned by a tool handler."""

    success: bool
    message: str
    ws_events: list[dict] = field(default_factory=list)


def handle_tool_call(tool_name: str, arguments: dict, session_state: dict) -> ToolResult:
    """Dispatch a validated tool call to the appropriate handler.

    Handlers modify session_state in-place. The engine persists state to disk.
    """

    if tool_name == "generate_action_cards":
        return handle_generate_action_cards(arguments, session_state)
    if tool_name == "generate_decision_quiz":
        return handle_generate_decision_quiz(arguments, session_state)
    if tool_name == "update_kanban":
        return handle_update_kanban(arguments, session_state)

    return ToolResult(success=False, message=f"Unknown tool: '{tool_name}'")


def handle_generate_action_cards(arguments: dict, session_state: dict) -> ToolResult:
    """Create action cards and add them to the pending list in session_state.

    Does not broadcast events — returns ws_events for the engine to broadcast.
    Does not write to disk — the engine persists state.
    """

    cards_data = arguments.get("cards", [])
    created = []

    seen_roles: dict[str, int] = {}
    for i, card in enumerate(cards_data):
        role_id = card["target_role_id"]
        if role_id in seen_roles:
            raise ToolValidationError(
                f"generate_action_cards: duplicate target_role_id '{role_id}' "
                f"at index {i} (first seen at index {seen_roles[role_id]}). "
                "Emit exactly one card per target agent per turn."
            )
        seen_roles[role_id] = i

    for card_data in cards_data:
        card = ActionCard(
            card_id=uuid4(),
            target_role_id=card_data["target_role_id"],
            prompt_text=card_data["prompt_text"],
            context_note=card_data["context_note"],
            linked_question_ids=card_data.get("linked_question_ids", []),
            status="PENDING",
        )
        card_dict = card.model_dump(mode="json")
        session_state.setdefault("pending_action_cards", []).append(card_dict)
        created.append(card_dict)

    ws_events = [{"event": "action_cards_created", "data": {"cards": created}}]
    return ToolResult(
        success=True,
        message=f"Created {len(created)} action card(s)",
        ws_events=ws_events,
    )


def handle_generate_decision_quiz(arguments: dict, session_state: dict) -> ToolResult:
    """Create a decision quiz and add it to the pending list in session_state."""

    quiz = DecisionQuiz(
        quiz_id=uuid4(),
        decision_title=arguments["decision_title"],
        options=arguments["options"],
        allow_freeform=arguments.get("allow_freeform", True),
        context_summary=arguments["context_summary"],
        linked_question_ids=arguments.get("linked_question_ids", []),
    )
    quiz_dict = quiz.model_dump(mode="json")
    session_state.setdefault("pending_quizzes", []).append(quiz_dict)

    ws_events = [{"event": "decision_quiz_created", "data": {"quiz": quiz_dict}}]
    return ToolResult(success=True, message="Created decision quiz", ws_events=ws_events)


def handle_update_kanban(arguments: dict, session_state: dict) -> ToolResult:
    """Update kanban task statuses and notes in session_state."""

    updates = arguments.get("updates", [])
    kanban = session_state.get("kanban", {})
    task_map = {task["task_id"]: task for task in kanban.get("tasks", [])}

    applied: list[str] = []
    for update in updates:
        qid = update["question_id"]
        if qid in task_map:
            task_map[qid]["status"] = update["new_status"]
            if "notes" in update:
                task_map[qid]["notes"] = update["notes"]
            applied.append(qid)

    ws_events = [{"event": "kanban_updated", "data": {"kanban": kanban}}]
    return ToolResult(
        success=True,
        message=f"Updated {len(applied)} kanban task(s)",
        ws_events=ws_events,
    )


def _serialize(obj: object) -> str:
    """Serialize an object to a JSON string for display in error messages."""

    return json.dumps(obj, indent=2, default=str)
