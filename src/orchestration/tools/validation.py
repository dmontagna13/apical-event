"""Moderator tool call validation."""

from __future__ import annotations

_KNOWN_TOOLS = {"generate_action_cards", "generate_decision_quiz", "update_kanban"}

_VALID_KANBAN_STATUSES = {
    "TO_DISCUSS",
    "AGENT_DELIBERATION",
    "PENDING_HUMAN_DECISION",
    "RESOLVED",
}


class ToolValidationError(ValueError):
    """Raised when tool handler arguments violate behavioral constraints."""


def validate_tool_call(tool_name: str, arguments: dict, session_state: dict) -> list[str]:
    """Validate a tool call against its schema and session context.

    Returns a list of error strings (empty on success).
    Checks: known tool name, required fields, role existence, moderator exclusion,
    question_id existence, valid status enums.
    """

    if tool_name not in _KNOWN_TOOLS:
        return [f"Unknown tool: '{tool_name}'. Valid tools: {sorted(_KNOWN_TOOLS)}"]

    if tool_name == "generate_action_cards":
        return _validate_action_cards(arguments, session_state)
    if tool_name == "generate_decision_quiz":
        return _validate_decision_quiz(arguments)
    if tool_name == "update_kanban":
        return _validate_update_kanban(arguments, session_state)

    return []  # unreachable given the check above


def validate_tool_semantics(tool_name: str, arguments: dict, session_state: dict) -> list[str]:
    """Validate tool arguments against behavioral rules beyond schema checks."""

    errors: list[str] = []

    if tool_name == "generate_action_cards":
        cards = arguments.get("cards", [])
        if not isinstance(cards, list):
            return ["'cards' must be an array"]
        seen: set[str] = set()
        moderator_id: str | None = session_state.get("moderator_role_id")
        for index, card in enumerate(cards):
            target = card.get("target_role_id")
            if not target:
                continue
            if target in seen:
                errors.append(
                    f"cards[{index}]: duplicate target_role_id '{target}'. "
                    "Emit exactly one card per target agent per turn."
                )
            else:
                seen.add(target)
            if moderator_id and target == moderator_id:
                errors.append(
                    f"cards[{index}]: target_role_id cannot be the moderator role '{moderator_id}'"
                )
        return errors

    if tool_name == "update_kanban":
        updates = arguments.get("updates", [])
        if not isinstance(updates, list):
            return ["'updates' must be an array"]
        kanban = session_state.get("kanban", {})
        task_ids = {task["task_id"] for task in kanban.get("tasks", [])}
        for index, update in enumerate(updates):
            qid = update.get("question_id")
            if qid and task_ids and qid not in task_ids:
                errors.append(f"updates[{index}]: question_id '{qid}' not found in kanban")
        return errors

    if tool_name == "generate_decision_quiz":
        options = arguments.get("options", [])
        if not isinstance(options, list) or len(options) < 2:
            errors.append("'options' must contain at least 2 entries")
        return errors

    return errors


def _validate_action_cards(arguments: dict, session_state: dict) -> list[str]:
    errors: list[str] = []

    if "cards" not in arguments:
        return ["Missing required field: 'cards'"]

    cards = arguments["cards"]
    if not isinstance(cards, list):
        return ["'cards' must be an array"]

    all_role_ids: list[str] = session_state.get("all_role_ids", [])
    moderator_id: str | None = session_state.get("moderator_role_id")

    for i, card in enumerate(cards):
        prefix = f"cards[{i}]"
        for field in ("target_role_id", "prompt_text", "context_note"):
            if field not in card or not card[field]:
                errors.append(f"{prefix}: missing required field '{field}'")

        target = card.get("target_role_id")
        if target:
            if all_role_ids and target not in all_role_ids:
                errors.append(f"{prefix}: target_role_id '{target}' is not a valid session role")
            elif moderator_id and target == moderator_id:
                errors.append(
                    f"{prefix}: target_role_id cannot be the moderator role '{moderator_id}'"
                )

    return errors


def _validate_decision_quiz(arguments: dict) -> list[str]:
    errors: list[str] = []

    for field in ("decision_title", "context_summary"):
        if field not in arguments or not arguments[field]:
            errors.append(f"Missing required field: '{field}'")

    if "options" not in arguments:
        errors.append("Missing required field: 'options'")
    elif not isinstance(arguments["options"], list) or len(arguments["options"]) == 0:
        errors.append("'options' must be a non-empty array")

    return errors


def _validate_update_kanban(arguments: dict, session_state: dict) -> list[str]:
    errors: list[str] = []

    if "updates" not in arguments:
        return ["Missing required field: 'updates'"]

    updates = arguments["updates"]
    if not isinstance(updates, list):
        return ["'updates' must be an array"]

    kanban = session_state.get("kanban", {})
    task_ids = {task["task_id"] for task in kanban.get("tasks", [])}

    for i, update in enumerate(updates):
        prefix = f"updates[{i}]"

        if "question_id" not in update:
            errors.append(f"{prefix}: missing required field 'question_id'")
        elif task_ids and update["question_id"] not in task_ids:
            errors.append(f"{prefix}: question_id '{update['question_id']}' not found in kanban")

        if "new_status" not in update:
            errors.append(f"{prefix}: missing required field 'new_status'")
        elif update.get("new_status") not in _VALID_KANBAN_STATUSES:
            errors.append(
                f"{prefix}: invalid status '{update.get('new_status')}'. "
                f"Valid: {sorted(_VALID_KANBAN_STATUSES)}"
            )

    return errors
