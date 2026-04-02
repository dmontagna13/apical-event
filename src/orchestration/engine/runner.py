"""Orchestration engine runner — init dispatch and LangGraph entry (§4.3/§4.4)."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from api.websocket.events import init_dispatch_complete, init_dispatch_started
from core.config import ProviderConfig, load_providers, resolve_api_key
from core.journals import append_turn, load_state, read_journal, save_state
from core.journals.session_dir import load_packet, load_roll_call
from core.prompt_assembly.agent_prompt import assemble_agent_prompt
from core.prompt_assembly.moderator_prompt import assemble_moderator_prompt
from core.providers.base import Message, ProviderError
from core.providers.factory import get_adapter
from core.schemas import AgentTurn, RollCall, SessionPacket
from core.schemas.constants import AGENT_TIMEOUT_SECONDS
from core.schemas.enums import SessionState, SessionSubstate, TurnType
from orchestration.engine.graph import build_graph
from orchestration.engine.state import RUNTIME_KEY, strip_runtime
from orchestration.tools.definitions import get_tool_definitions

logger = logging.getLogger(__name__)

_human_gate_queues: dict[str, asyncio.Queue] = {}


async def start_session(
    session_id: str,
    data_root: Path,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
) -> None:
    """Assemble init prompts, dispatch all roles, then enter the graph."""

    session_dir = _find_session_dir(data_root, session_id)
    packet = load_packet(session_dir)
    roll_call = load_roll_call(session_dir)

    providers_config = load_providers(data_root)
    state = load_state(session_dir)
    state["session_dir"] = str(session_dir)
    state["state"] = SessionState.ACTIVE.value
    state["substate"] = SessionSubstate.INIT_DISPATCH.value
    state["is_cycle_one"] = True
    save_state(session_dir, strip_runtime(state))

    await broadcast_fn(
        session_id,
        {"event": "session_started", "data": {"substate": SessionSubstate.INIT_DISPATCH.value}},
    )
    await broadcast_fn(session_id, init_dispatch_started_event(packet))

    init_results = await _dispatch_init_prompts(
        session_dir=session_dir,
        packet=packet,
        roll_call=roll_call,
        providers_config=providers_config,
        state=state,
        broadcast_fn=broadcast_fn,
    )

    success_count = sum(1 for result in init_results if result["status"] == "OK")
    error_count = len(init_results) - success_count
    await broadcast_fn(session_id, init_dispatch_complete(success_count, error_count))

    state["substate"] = SessionSubstate.AGENT_AGGREGATION.value
    save_state(session_dir, strip_runtime(state))

    queue = _human_gate_queues.setdefault(session_id, asyncio.Queue())
    state[RUNTIME_KEY] = {
        "data_root": data_root,
        "broadcast": broadcast_fn,
        "human_queue": queue,
    }

    graph = build_graph()
    await graph.ainvoke(state, config={"entry_point": "agent_aggregation"})


async def resume_session(
    session_id: str,
    data_root: Path,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
) -> None:
    """Resume a session from persisted state.json."""

    session_dir = _find_session_dir(data_root, session_id)
    state = load_state(session_dir)
    state["session_dir"] = str(session_dir)
    substate = state.get("substate")

    if substate == SessionSubstate.INIT_DISPATCH.value:
        if _no_init_turns(session_dir):
            await start_session(session_id, data_root, broadcast_fn)
            return
        _fill_missing_init_turns(session_dir, state)
        state["is_cycle_one"] = True
        state["substate"] = SessionSubstate.AGENT_AGGREGATION.value
        save_state(session_dir, strip_runtime(state))

    elif substate == SessionSubstate.AGENT_DISPATCH.value:
        logger.error("Session %s crashed during AGENT_DISPATCH — entering ERROR", session_id)
        state["state"] = SessionState.ERROR.value
        state["substate"] = None
        state["error"] = (
            "Server crashed during AGENT_DISPATCH. Partial agent responses may exist. "
            "This is a v1 limitation — start a new session."
        )
        save_state(session_dir, strip_runtime(state))
        await broadcast_fn(
            session_id,
            {
                "event": "error",
                "data": {
                    "code": "INTERNAL_ERROR",
                    "message": "Session crashed during agent dispatch",
                    "recoverable": False,
                },
            },
        )
        return

    queue = _human_gate_queues.setdefault(session_id, asyncio.Queue())
    state[RUNTIME_KEY] = {
        "data_root": data_root,
        "broadcast": broadcast_fn,
        "human_queue": queue,
    }

    entry_point = _entry_point_for_substate(substate)
    if entry_point is None:
        logger.error("Session %s has no resumable substate: %s", session_id, substate)
        return

    graph = build_graph()
    await graph.ainvoke(state, config={"entry_point": entry_point})


async def signal_human_gate(session_id: str, event_data: dict) -> bool:
    """Deliver an event to the waiting human gate queue."""

    queue = _human_gate_queues.get(session_id)
    if queue is None:
        return False
    await queue.put(event_data)
    return True


def _entry_point_for_substate(substate: str | None) -> str | None:
    if substate == SessionSubstate.MODERATOR_TURN.value:
        return "moderator_turn"
    if substate == SessionSubstate.HUMAN_GATE.value:
        return "human_gate"
    if substate == SessionSubstate.AGENT_AGGREGATION.value:
        return "agent_aggregation"
    if substate == SessionSubstate.AGENT_DISPATCH.value:
        return None
    if substate == SessionSubstate.INIT_DISPATCH.value:
        return "agent_aggregation"
    return None


async def _dispatch_init_prompts(
    session_dir: Path,
    packet: SessionPacket,
    roll_call: RollCall,
    providers_config: dict[str, ProviderConfig],
    state: dict,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
) -> list[dict]:
    assignment_map = {a.role_id: a for a in roll_call.assignments}
    moderator_role = next(role for role in packet.roles if role.is_moderator)
    tools = get_tool_definitions()
    tool_defs_text = _format_tool_definitions(tools)
    kanban_state_text = _format_kanban(state.get("kanban", {}))
    non_moderator_role_ids = [r.role_id for r in packet.roles if not r.is_moderator]

    tasks = []
    for role in packet.roles:
        assignment = assignment_map[role.role_id]
        provider_cfg = providers_config[assignment.provider]
        tasks.append(
            asyncio.create_task(
                _dispatch_init_role(
                    session_dir=session_dir,
                    session_id=state["session_id"],
                    role=role,
                    assignment=assignment,
                    provider_cfg=provider_cfg,
                    packet=packet,
                    moderator_role=moderator_role,
                    tool_defs_text=tool_defs_text,
                    kanban_state_text=kanban_state_text,
                    non_moderator_role_ids=non_moderator_role_ids,
                )
            )
        )

    results: list[dict] = []
    for task in asyncio.as_completed(tasks):
        result = await task
        results.append(result)
        if result["is_moderator"]:
            _update_moderator_state(state, result)
        if result["is_moderator"] and result["response_text"]:
            await broadcast_fn(
                state["session_id"],
                {"event": "moderator_turn", "data": {"text": result["response_text"]}},
            )
        elif not result["is_moderator"]:
            await broadcast_fn(
                state["session_id"],
                {
                    "event": "agent_response",
                    "data": {
                        "role_id": result["role_id"],
                        "response_text": result["response_text"],
                        "status": result["status"],
                        "error_message": result["error_message"],
                        "latency_ms": result["latency_ms"],
                        "turn_id": result["turn_id"],
                    },
                },
            )

    return results


async def _dispatch_init_role(
    session_dir: Path,
    session_id: str,
    role,
    assignment,
    provider_cfg: ProviderConfig,
    packet: SessionPacket,
    moderator_role,
    tool_defs_text: str,
    kanban_state_text: str,
    non_moderator_role_ids: list[str],
) -> dict:
    api_key = resolve_api_key(provider_cfg)
    resolved_cfg = provider_cfg.model_copy(update={"api_key": api_key})
    adapter = get_adapter(assignment.provider, resolved_cfg)

    if role.is_moderator:
        system_prompt = assemble_moderator_prompt(
            packet=packet,
            role=moderator_role,
            non_moderator_role_ids=non_moderator_role_ids,
            tool_definitions_text=tool_defs_text,
            kanban_state=kanban_state_text,
        )
        user_message = _build_moderator_init_message(packet)
    else:
        system_prompt = assemble_agent_prompt(packet, role)
        user_message = (
            "The session is beginning. You will receive your first question shortly. "
            "Briefly introduce yourself in your assigned role and confirm you are ready."
        )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_message),
    ]

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
        logger.error("Init dispatch error for role %s: %s", role.role_id, exc)

    agent_turn = AgentTurn(
        turn_id=turn_id,
        session_id=session_id,
        role_id=role.role_id,
        turn_type=TurnType.INIT,
        bundle_id=None,
        prompt_hash="",
        approved_prompt=user_message,
        agent_response=response_text,
        status=status,
        error_message=error_message,
        metadata=metadata,
    )
    append_turn(session_dir, role.role_id, agent_turn)

    return {
        "role_id": role.role_id,
        "turn_id": str(turn_id),
        "response_text": response_text,
        "status": status,
        "error_message": error_message,
        "latency_ms": metadata.get("latency_ms", 0),
        "is_moderator": role.is_moderator,
        "user_message": user_message,
    }


def init_dispatch_started_event(packet: SessionPacket) -> dict:
    role_ids = [role.role_id for role in packet.roles]
    return init_dispatch_started(role_ids)


def _update_moderator_state(state: dict, result: dict) -> None:
    user_message = result["user_message"]
    assistant_message = result["response_text"] or ""
    state["moderator_messages"] = [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_message},
    ]
    if assistant_message:
        state.setdefault("chat_history", []).append(
            {"role": "moderator", "content": assistant_message}
        )


def _build_moderator_init_message(packet: SessionPacket) -> str:
    agenda_lines = "\n".join(
        f"{index + 1}. {item.text}" for index, item in enumerate(packet.agenda)
    )
    return (
        f"Objective: {packet.objective}\n\n"
        f"Agenda:\n{agenda_lines}\n\n"
        "Begin the session. Greet the facilitator, summarize the agenda, and indicate "
        "that you are waiting for the panel's opening positions."
    )


def _format_kanban(kanban: dict) -> str:
    tasks = kanban.get("tasks", [])
    if not tasks:
        return "(no tasks)"
    lines = ["| task_id | status | title |", "|---------|--------|-------|"]
    for task in tasks:
        lines.append(
            f"| {task.get('task_id', '')} | {task.get('status', '')} | "
            f"{task.get('title', '')} |"
        )
    return "\n".join(lines)


def _format_tool_definitions(tools: list) -> str:
    import json

    return json.dumps(
        [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools],
        indent=2,
    )


def _find_session_dir(data_root: Path, session_id: str) -> Path:
    for project_dir in (data_root / "projects").glob("*"):
        session_dir = project_dir / "sessions" / session_id
        if session_dir.exists():
            return session_dir
    raise FileNotFoundError(f"Session not found: {session_id}")


def _no_init_turns(session_dir: Path) -> bool:
    from core.journals import read_all_journals

    journals = read_all_journals(session_dir)
    return all(len(journal.turns) == 0 for journal in journals)


def _fill_missing_init_turns(session_dir: Path, state: dict) -> None:
    packet = load_packet(session_dir)
    for role in packet.roles:
        journal = read_journal(session_dir, role.role_id)
        if journal.turns:
            continue
        user_message = (
            _build_moderator_init_message(packet)
            if role.is_moderator
            else (
                "The session is beginning. You will receive your first question shortly. "
                "Briefly introduce yourself in your assigned role and confirm you are ready."
            )
        )
        agent_turn = AgentTurn(
            turn_id=uuid4(),
            session_id=state["session_id"],
            role_id=role.role_id,
            turn_type=TurnType.INIT,
            bundle_id=None,
            prompt_hash="",
            approved_prompt=user_message,
            agent_response="",
            status="TIMEOUT",
            error_message="Init dispatch incomplete before restart",
            metadata={"latency_ms": 0},
        )
        append_turn(session_dir, role.role_id, agent_turn)
