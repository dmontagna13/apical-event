"""AGENT_DISPATCH node — parallel agent API calls (§4.4.4)."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from uuid import uuid4

from api.websocket.manager import ConnectionManager
from core.config import ProviderConfig, resolve_api_key
from core.journals import append_turn, next_bundle_id, read_journal
from core.prompt_assembly.agent_prompt import assemble_agent_prompt
from core.providers.base import Message, ProviderError
from core.providers.factory import get_adapter
from core.schemas import AgentTurn, RollCall, SessionPacket
from core.schemas.constants import AGENT_TIMEOUT_SECONDS
from core.schemas.enums import SessionSubstate, TurnType

logger = logging.getLogger(__name__)


async def run_agent_dispatch(
    session_dir: Path,
    state: dict,
    manager: ConnectionManager,
    providers_config: dict[str, ProviderConfig],
) -> dict:
    """Dispatch approved cards to background agents in parallel.

    For each approved card, calls the target agent's LLM provider, writes the
    result to the agent's journal, and broadcasts a per-agent response event.
    Timeouts and errors are captured as ERROR status (not raised).

    Updates state with dispatch_results and current_bundle_id.
    """

    session_id = state["session_id"]
    packet = _load_packet(session_dir)
    roll_call = _load_roll_call(session_dir)

    approved_cards: list[dict] = state.get("approved_cards", [])
    bundle_id = next_bundle_id(session_dir)
    state["current_bundle_id"] = bundle_id

    # Build a map: role_id → assignment
    assignment_map = {a.role_id: a for a in roll_call.assignments}

    tasks = [
        _dispatch_one(
            session_dir=session_dir,
            session_id=session_id,
            packet=packet,
            card=card,
            bundle_id=bundle_id,
            assignment_map=assignment_map,
            providers_config=providers_config,
            manager=manager,
        )
        for card in approved_cards
    ]

    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    dispatch_results: list[dict] = []
    for card, result in zip(approved_cards, raw_results):
        if isinstance(result, Exception):
            logger.error(
                "Unhandled exception dispatching %s: %s",
                card.get("target_role_id"),
                result,
            )
            dispatch_results.append(
                {
                    "role_id": card.get("target_role_id", "unknown"),
                    "turn_id": str(uuid4()),
                    "response_text": "",
                    "status": "ERROR",
                    "error_message": str(result),
                    "latency_ms": 0,
                }
            )
        else:
            dispatch_results.append(result)

    state["dispatch_results"] = dispatch_results
    state["substate"] = SessionSubstate.AGENT_AGGREGATION.value

    return state


async def _dispatch_one(
    session_dir: Path,
    session_id: str,
    packet: SessionPacket,
    card: dict,
    bundle_id: str,
    assignment_map: dict,
    providers_config: dict[str, ProviderConfig],
    manager: ConnectionManager,
) -> dict:
    """Call one agent and return a dispatch_result dict."""

    role_id = card["target_role_id"]
    approved_prompt = card.get("human_modified_prompt") or card["prompt_text"]

    assignment = assignment_map.get(role_id)
    if assignment is None:
        return _error_result(role_id, f"No assignment found for role_id '{role_id}'")

    role = next((r for r in packet.roles if r.role_id == role_id), None)
    if role is None:
        return _error_result(role_id, f"Role '{role_id}' not found in packet")

    provider_cfg = providers_config.get(assignment.provider)
    if provider_cfg is None:
        return _error_result(role_id, f"Provider '{assignment.provider}' not configured")

    api_key = resolve_api_key(provider_cfg)
    resolved_cfg = provider_cfg.model_copy(update={"api_key": api_key})
    adapter = get_adapter(assignment.provider, resolved_cfg)

    # Build agent messages: system prompt + prior journal turns + new prompt
    system_prompt = assemble_agent_prompt(packet, role)
    messages: list[Message] = [Message(role="system", content=system_prompt)]

    journal = read_journal(session_dir, role_id)
    for turn in journal.turns:
        messages.append(Message(role="user", content=turn.approved_prompt))
        messages.append(Message(role="assistant", content=turn.agent_response))

    messages.append(Message(role="user", content=approved_prompt))

    turn_id = uuid4()
    start = time.monotonic()
    response_text = ""
    status = "OK"
    error_message = None
    metadata: dict = {}

    try:
        result = await asyncio.wait_for(
            adapter.complete(messages, assignment.model),
            timeout=AGENT_TIMEOUT_SECONDS,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        response_text = result.text
        metadata = {**result.usage, "latency_ms": latency_ms, "finish_reason": result.finish_reason}

    except asyncio.TimeoutError:
        latency_ms = int((time.monotonic() - start) * 1000)
        status = "TIMEOUT"
        error_message = f"Agent timed out after {AGENT_TIMEOUT_SECONDS}s"
        metadata = {"latency_ms": latency_ms}
        logger.warning("Agent %s timed out for session %s", role_id, session_id)

    except ProviderError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        status = "ERROR"
        error_message = str(exc)
        metadata = {"latency_ms": latency_ms}
        logger.error(
            "Provider %s error for session %s (model %s): %s",
            exc.provider,
            session_id,
            exc.model,
            exc.response_body or exc,
        )

    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.monotonic() - start) * 1000)
        status = "ERROR"
        error_message = str(exc)
        metadata = {"latency_ms": latency_ms}
        logger.error("Agent %s error for session %s: %s", role_id, session_id, exc)

    # Write turn to journal
    agent_turn = AgentTurn(
        turn_id=turn_id,
        session_id=session_id,
        role_id=role_id,
        turn_type=TurnType.DELIBERATION,
        bundle_id=bundle_id,
        prompt_hash="",  # computed by append_turn
        approved_prompt=approved_prompt,
        agent_response=response_text,
        status=status,
        error_message=error_message,
        metadata=metadata,
    )
    append_turn(session_dir, role_id, agent_turn)

    # Broadcast per-agent event
    await manager.broadcast(
        session_id,
        {
            "event": "agent_response",
            "data": {
                "role_id": role_id,
                "response_text": response_text,
                "status": status,
                "error_message": error_message,
                "latency_ms": latency_ms,
                "turn_id": str(turn_id),
            },
        },
    )

    return {
        "role_id": role_id,
        "turn_id": str(turn_id),
        "response_text": response_text,
        "status": status,
        "error_message": error_message,
        "latency_ms": latency_ms,
    }


def _error_result(role_id: str, message: str) -> dict:
    return {
        "role_id": role_id,
        "turn_id": str(uuid4()),
        "response_text": "",
        "status": "ERROR",
        "error_message": message,
        "latency_ms": 0,
    }


def _load_packet(session_dir: Path) -> SessionPacket:
    from core.journals.session_dir import load_packet

    return load_packet(session_dir)


def _load_roll_call(session_dir: Path) -> RollCall:
    from core.journals.session_dir import load_roll_call

    return load_roll_call(session_dir)


# LangGraph-compatible stub for graph.py topology definition
async def agent_dispatch_node(state: dict) -> dict:
    """LangGraph stub.  Actual dispatch requires injected dependencies — see runner.py."""

    return state
