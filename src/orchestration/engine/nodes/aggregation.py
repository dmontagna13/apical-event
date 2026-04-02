"""AGENT_AGGREGATION node — bundle construction and state cleanup (§4.4.5)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from api.websocket.manager import ConnectionManager
from core.journals import write_bundle
from core.schemas import AgentResponseBundle, BundledResponse
from core.schemas.enums import BundleType, SessionSubstate

logger = logging.getLogger(__name__)


async def run_agent_aggregation(
    session_dir: Path,
    state: dict,
    manager: ConnectionManager,
) -> dict:
    """Build the bundle from dispatch results, write it to disk, and transition.

    Collects the dispatch_results stored by dispatch_node, constructs an
    AgentResponseBundle, writes it to disk, updates the moderator's conversation
    history with the bundle as a new user message, and sets substate to
    MODERATOR_TURN.
    """

    session_id = state["session_id"]
    bundle_id: str = state.get("current_bundle_id", "bundle_001")
    dispatch_results: list[dict] = state.get("dispatch_results", [])

    # Build BundledResponse list
    responses: list[BundledResponse] = []
    for r in dispatch_results:
        responses.append(
            BundledResponse(
                role_id=r["role_id"],
                turn_id=UUID(r["turn_id"]) if r.get("turn_id") else UUID(int=0),
                response_text=r.get("response_text", ""),
                status=r.get("status", "ERROR"),
                error_message=r.get("error_message"),
                latency_ms=r.get("latency_ms", 0),
            )
        )

    bundle = AgentResponseBundle(
        bundle_id=bundle_id,
        bundle_type=BundleType.DELIBERATION,
        timestamp=datetime.now(tz=timezone.utc),
        responses=responses,
    )
    write_bundle(session_dir, bundle)

    # Format bundle as text for the moderator's conversation history
    bundle_text = _format_bundle(bundle)

    # Append the bundle as the next user message in moderator conversation history
    moderator_messages: list[dict] = list(state.get("moderator_messages", []))
    moderator_messages.append({"role": "user", "content": bundle_text})
    state["moderator_messages"] = moderator_messages

    # Broadcast bundle_ready event
    await manager.broadcast(
        session_id,
        {
            "event": "bundle_ready",
            "data": {
                "bundle_id": bundle_id,
                "responses": [r.model_dump(mode="json") for r in responses],
            },
        },
    )

    # Clean up dispatch state
    state["dispatch_results"] = []
    state["approved_cards"] = []
    state["substate"] = SessionSubstate.MODERATOR_TURN.value

    return state


def _format_bundle(bundle: AgentResponseBundle) -> str:
    """Format an AgentResponseBundle as a human-readable text block."""

    lines = [f"AGENT RESPONSES ({bundle.bundle_id}) — {bundle.timestamp.isoformat()}:"]
    for r in bundle.responses:
        status_note = "" if r.status == "OK" else f" [{r.status}]"
        lines.append(f"\n--- {r.role_id}{status_note} ---")
        if r.status == "OK":
            lines.append(r.response_text)
        elif r.error_message:
            lines.append(f"(error: {r.error_message})")
        else:
            lines.append("(no response)")
    return "\n".join(lines)


# LangGraph-compatible stub for graph.py topology definition
async def agent_aggregation_node(state: dict) -> dict:
    """LangGraph stub.  Actual aggregation requires injected dependencies — see runner.py."""

    return state
