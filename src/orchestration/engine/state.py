"""LangGraph state definition for the deliberation engine."""

from __future__ import annotations

from typing import TypedDict


class GraphState(TypedDict, total=False):
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

    # Error message if the session entered ERROR state
    error: str

    # Current substate (mirrors state.json["substate"])
    substate: str
