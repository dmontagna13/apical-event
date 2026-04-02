"""LangGraph state definition for the deliberation engine."""

from __future__ import annotations

from typing import Any, TypedDict

RUNTIME_KEY = "_runtime"


class EngineStateError(RuntimeError):
    """Raised when the engine state violates a graph invariant."""


class EngineState(TypedDict, total=False):
    """State carried between graph nodes.

    All fields are optional (total=False) because nodes update only a subset
    of fields on each transition.  The runner persists the full state dict to
    state.json after every node transition.

    Invariant: `session_dir` and `session_id` are always present after init.
    """

    session_id: str
    session_dir: str  # str path — TypedDict can't hold Path

    # Session context (derived from packet + roll_call at start, static after)
    moderator_role_id: str
    all_role_ids: list[str]
    non_moderator_role_ids: list[str]

    # Mutable deliberation state (mirrors state.json on disk)
    kanban: dict
    pending_action_cards: list[dict]
    pending_quizzes: list[dict]
    chat_history: list[dict]
    queued_human_messages: list[dict]

    # Moderator LLM conversation history (user/assistant message pairs)
    moderator_messages: list[dict]

    # Set by human_gate after the user clicks "Send Approved"
    approved_cards: list[dict]

    # Set by dispatch_node; read by aggregation_node
    dispatch_results: list[dict]
    current_bundle_id: str

    # Latest bundled payload (used to enforce moderator entry invariant)
    latest_bundle: dict[str, Any] | None

    # Error message if the session entered ERROR state
    error: str

    # Current substate (mirrors state.json["substate"])
    substate: str

    # True from session start until AGENT_AGGREGATION completes for the first time.
    is_cycle_one: bool


def strip_runtime(state: dict) -> dict:
    """Return a shallow copy of state without runtime-only keys."""

    if RUNTIME_KEY not in state:
        return state
    cleaned = dict(state)
    cleaned.pop(RUNTIME_KEY, None)
    return cleaned
