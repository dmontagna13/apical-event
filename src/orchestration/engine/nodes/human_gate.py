"""HUMAN_GATE node — pure state-transition logic for human approvals (§4.4.3).

This module contains only the synchronous state-transformation logic.  The
*waiting* for WebSocket events is handled by the runner (runner.py), which
owns the asyncio.Queue and calls process_gate_event() once an event arrives.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.journals import save_state
from core.schemas.enums import SessionState, SessionSubstate
from orchestration.engine.state import RUNTIME_KEY, strip_runtime


def process_gate_event(state: dict, event: dict) -> tuple[dict, str]:
    """Apply a human gate event to state and return (updated_state, next_substate).

    Args:
        state:  Current session state dict (modified in-place and returned).
        event:  Dict with ``type`` key:
                - ``"dispatch_approved"``: user clicked Send Approved.
                  Contains ``card_resolutions`` list and optional ``quiz_answers``.
                - ``"chat_message"``: user sent a chat message.
                  Contains ``content`` string.

    Returns:
        Tuple of (updated state dict, next substate string).
        Next substate is one of: "AGENT_DISPATCH", "MODERATOR_TURN".
    """

    event_type = event.get("type")

    if event_type == "chat_message":
        return _handle_chat(state, event)

    if event_type == "dispatch_approved":
        return _handle_dispatch_approved(state, event)

    # Unknown event type — treat as chat
    return _handle_chat(state, {"content": str(event)})


def _handle_chat(state: dict, event: dict) -> tuple[dict, str]:
    """Add the chat message to queued_human_messages and route to MODERATOR_TURN."""

    content = event.get("content", "")
    state.setdefault("chat_history", []).append({"role": "human", "content": content})
    state.setdefault("queued_human_messages", []).append(content)
    state["substate"] = "MODERATOR_TURN"
    return state, "MODERATOR_TURN"


def _handle_dispatch_approved(state: dict, event: dict) -> tuple[dict, str]:
    """Apply card resolutions, determine routing."""

    now = datetime.now(tz=timezone.utc).isoformat()
    card_resolutions: list[dict] = event.get("card_resolutions", [])
    quiz_answers: list[dict] = event.get("quiz_answers", [])

    # Index current pending cards by card_id
    pending: list[dict] = state.get("pending_action_cards", [])
    card_map = {str(c["card_id"]): c for c in pending}

    approved_cards: list[dict] = []

    for resolution in card_resolutions:
        card_id = str(resolution.get("card_id", ""))
        action = resolution.get("action", "")
        card = card_map.get(card_id)
        if card is None:
            continue

        if action == "APPROVED":
            card["status"] = "APPROVED"
            card["resolved_at"] = now
            approved_cards.append(card)
        elif action == "MODIFIED":
            card["status"] = "MODIFIED"
            card["human_modified_prompt"] = resolution.get("modified_prompt", card["prompt_text"])
            card["resolved_at"] = now
            approved_cards.append(card)
        elif action == "DENIED":
            card["status"] = "DENIED"
            card["denial_reason"] = resolution.get("denial_reason", "")
            card["resolved_at"] = now

    # Apply quiz answers
    quiz_map = {str(q["quiz_id"]): q for q in state.get("pending_quizzes", [])}
    for answer in quiz_answers:
        qid = str(answer.get("quiz_id", ""))
        quiz = quiz_map.get(qid)
        if quiz is None:
            continue
        quiz["selected_option"] = answer.get("selected_option")
        quiz["freeform_text"] = answer.get("freeform_text")
        quiz["resolved"] = True
        quiz["resolved_at"] = now

    state["pending_action_cards"] = list(card_map.values())

    if approved_cards:
        state["approved_cards"] = approved_cards
        state["substate"] = "AGENT_DISPATCH"
        return state, "AGENT_DISPATCH"

    # All cards denied — return to moderator with denial context
    denial_reasons = [
        f"Card for {c.get('target_role_id')}: {c.get('denial_reason', 'denied')}"
        for c in card_map.values()
        if c.get("status") == "DENIED"
    ]
    if denial_reasons:
        denial_note = "Human denied all action cards:\n" + "\n".join(denial_reasons)
        state.setdefault("queued_human_messages", []).append(denial_note)

    state["approved_cards"] = []
    state["substate"] = "MODERATOR_TURN"
    return state, "MODERATOR_TURN"


async def human_gate_node(state: dict) -> dict:
    """Await a human gate event, update state, and return the new state."""

    runtime = state.get(RUNTIME_KEY, {})
    queue = runtime.get("human_queue")
    if queue is None:
        return state
    event = await queue.get()
    updated_state, _ = process_gate_event(state, event)

    session_dir = Path(updated_state["session_dir"])
    save_state(session_dir, strip_runtime(updated_state))
    return updated_state


def route_after_human_gate(state: dict) -> str:
    """Return the next node name after HUMAN_GATE based on state."""

    if state.get("state") == SessionState.CONSENSUS.value:
        return "consensus"
    if state.get("substate") == SessionSubstate.AGENT_DISPATCH.value:
        return "agent_dispatch"
    return "moderator_turn"

    return state
