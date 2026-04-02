"""AGENT_AGGREGATION node — bundle construction and state cleanup (§4.4.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable
from uuid import UUID

from core.journals import next_bundle_id, read_journal, save_state, write_bundle
from core.schemas import AgentResponseBundle, BundledResponse, SessionPacket
from core.schemas.enums import BundleType, SessionSubstate
from orchestration.engine.state import RUNTIME_KEY, strip_runtime


async def run_agent_aggregation(
    session_dir: Path,
    state: dict,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
) -> dict:
    """Build a response bundle and transition to MODERATOR_TURN."""

    session_id = state["session_id"]
    is_cycle_one = bool(state.get("is_cycle_one", False))
    packet = _load_packet(session_dir)

    if is_cycle_one:
        background_roles = [role.role_id for role in packet.roles if not role.is_moderator]
        responses = _collect_init_responses(session_dir, background_roles)
        bundle_type = BundleType.INIT
        bundle_text = _format_init_bundle(responses)
    else:
        responses = _collect_dispatch_responses(state.get("dispatch_results", []))
        bundle_type = BundleType.DELIBERATION
        bundle_text = _format_deliberation_bundle(responses)

    bundle_id = next_bundle_id(session_dir)
    bundle = AgentResponseBundle(
        bundle_id=bundle_id,
        bundle_type=bundle_type,
        timestamp=datetime.now(tz=timezone.utc),
        responses=responses,
    )
    write_bundle(session_dir, bundle)

    moderator_messages: list[dict] = list(state.get("moderator_messages", []))
    moderator_messages.append({"role": "user", "content": bundle_text})
    state["moderator_messages"] = moderator_messages

    await broadcast_fn(
        session_id,
        {
            "event": "bundle_ready",
            "data": {
                "bundle_id": bundle_id,
                "responses": [r.model_dump(mode="json") for r in responses],
            },
        },
    )

    state["latest_bundle"] = bundle.model_dump(mode="json")
    state["current_bundle_id"] = bundle_id
    state["dispatch_results"] = []
    state["approved_cards"] = []
    state["substate"] = SessionSubstate.MODERATOR_TURN.value
    if is_cycle_one:
        state["is_cycle_one"] = False

    return state


def _collect_init_responses(session_dir: Path, role_ids: list[str]) -> list[BundledResponse]:
    responses: list[BundledResponse] = []
    for role_id in role_ids:
        journal = read_journal(session_dir, role_id)
        if not journal.turns:
            responses.append(
                BundledResponse(
                    role_id=role_id,
                    turn_id=UUID(int=0),
                    response_text="",
                    status="TIMEOUT",
                    error_message="Init response missing",
                    latency_ms=0,
                )
            )
            continue
        turn = journal.turns[-1]
        responses.append(
            BundledResponse(
                role_id=role_id,
                turn_id=turn.turn_id,
                response_text=turn.agent_response,
                status=turn.status,
                error_message=turn.error_message,
                latency_ms=int(turn.metadata.get("latency_ms", 0)),
            )
        )
    return responses


def _collect_dispatch_responses(dispatch_results: list[dict]) -> list[BundledResponse]:
    responses: list[BundledResponse] = []
    for result in dispatch_results:
        responses.append(
            BundledResponse(
                role_id=result["role_id"],
                turn_id=UUID(result["turn_id"]) if result.get("turn_id") else UUID(int=0),
                response_text=result.get("response_text", ""),
                status=result.get("status", "ERROR"),
                error_message=result.get("error_message"),
                latency_ms=result.get("latency_ms", 0),
            )
        )
    return responses


def _format_init_bundle(responses: list[BundledResponse]) -> str:
    lines = ["Initial panel responses received."]
    for response in responses:
        status_note = "" if response.status == "OK" else f" [{response.status}]"
        if response.status == "OK":
            text = response.response_text
        else:
            text = response.error_message or "No response"
        lines.append(f"{response.role_id}{status_note}: {text}")
    return "\n".join(lines)


def _format_deliberation_bundle(responses: list[BundledResponse]) -> str:
    lines = [f"AGENT RESPONSES ({datetime.now(tz=timezone.utc).isoformat()}):"]
    for response in responses:
        status_note = "" if response.status == "OK" else f" [{response.status}]"
        lines.append(f"\n--- {response.role_id}{status_note} ---")
        if response.status == "OK":
            lines.append(response.response_text)
        elif response.error_message:
            lines.append(f"(error: {response.error_message})")
        else:
            lines.append("(no response)")
    return "\n".join(lines)


def _load_packet(session_dir: Path) -> SessionPacket:
    from core.journals.session_dir import load_packet

    return load_packet(session_dir)


async def agent_aggregation_node(state: dict) -> dict:
    """LangGraph node: aggregate responses into a bundle."""

    runtime = state.get(RUNTIME_KEY, {})
    broadcast_fn = runtime.get("broadcast") or _noop_broadcast
    session_dir = Path(state["session_dir"])

    updated_state = await run_agent_aggregation(session_dir, state, broadcast_fn)
    save_state(session_dir, strip_runtime(updated_state))
    return updated_state


async def _noop_broadcast(session_id: str, event: dict) -> None:
    return None
