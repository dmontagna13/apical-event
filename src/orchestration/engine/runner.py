"""Orchestration engine runner — manages the deliberation loop lifecycle.

DECISION: The runner implements the actual execution loop via a plain asyncio
loop rather than via LangGraph's compiled.ainvoke().  LangGraph's StateGraph
(graph.py) defines the topology for reference; the runner calls node functions
directly.  This gives us crash-resilient state management (via state.json) and
straightforward human-gate signalling (via asyncio.Queue) without needing
LangGraph's checkpoint infrastructure.

Crash semantics (v1 known limitation, documented here):
  - HUMAN_GATE: on resume, the session re-enters the wait state.  The
    pending_action_cards from state.json are still present.
  - AGENT_DISPATCH: if the server crashes mid-dispatch, the session is moved
    to ERROR state on resume.  Partial journal writes may have occurred.
  - MODERATOR_TURN: re-runs from the beginning of that turn.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from api.websocket.manager import ConnectionManager
from core.config import ProviderConfig, load_providers
from core.journals import load_state, save_state
from core.schemas.enums import SessionState, SessionSubstate

from .nodes.aggregation import run_agent_aggregation
from .nodes.dispatch import run_agent_dispatch
from .nodes.human_gate import process_gate_event
from .nodes.moderator import run_moderator_turn

logger = logging.getLogger(__name__)

# Module-level queues: session_id → asyncio.Queue
# Each queue receives one event dict when the human acts in HUMAN_GATE.
_human_gate_queues: dict[str, asyncio.Queue] = {}

# Running background tasks: session_id → asyncio.Task
_session_tasks: dict[str, asyncio.Task] = {}


async def start_session(
    session_dir: Path,
    data_root: Path,
    manager: ConnectionManager,
) -> None:
    """Launch the orchestration engine for a newly activated session.

    Schedules _run_graph as a background asyncio task.  Returns immediately.
    Called from the roll-call route after state transitions to ACTIVE.
    """

    state = load_state(session_dir)
    session_id = state["session_id"]

    if session_id in _session_tasks and not _session_tasks[session_id].done():
        logger.warning("Session %s already running — ignoring duplicate start", session_id)
        return

    task = asyncio.create_task(
        _run_graph(session_dir, session_id, data_root, manager),
        name=f"engine-{session_id}",
    )
    _session_tasks[session_id] = task
    task.add_done_callback(lambda t: _on_task_done(session_id, t))


async def resume_session(
    session_dir: Path,
    data_root: Path,
    manager: ConnectionManager,
) -> None:
    """Re-enter the engine loop for a session that was interrupted by a server restart.

    Reads state.json to determine the current substate:
    - MODERATOR_TURN / AGENT_AGGREGATION: re-run the loop from that substate.
    - HUMAN_GATE: re-register the gate queue and wait (no LLM call needed).
    - AGENT_DISPATCH: transition to ERROR (crash during dispatch — v1 limitation).
    """

    state = load_state(session_dir)
    session_id = state["session_id"]
    substate = state.get("substate")

    if substate == SessionSubstate.AGENT_DISPATCH.value:
        # DECISION: crash during dispatch → ERROR state.  Partial journals may exist.
        # Known limitation documented in spec §TASK-10.
        logger.error(
            "Session %s crashed during AGENT_DISPATCH — transitioning to ERROR", session_id
        )
        state["state"] = SessionState.ERROR.value
        state["substate"] = None
        state["error"] = (
            "Server crashed during AGENT_DISPATCH. Partial agent responses may exist in journals. "
            "This is a known v1 limitation — start a new session."
        )
        save_state(session_dir, state)
        await manager.broadcast(
            session_id,
            {"event": "error", "data": {
                "code": "INTERNAL_ERROR",
                "message": "Session crashed during agent dispatch",
                "recoverable": False,
            }},
        )
        return

    task = asyncio.create_task(
        _run_graph(session_dir, session_id, data_root, manager),
        name=f"engine-resume-{session_id}",
    )
    _session_tasks[session_id] = task
    task.add_done_callback(lambda t: _on_task_done(session_id, t))


async def signal_human_gate(session_id: str, event_data: dict) -> bool:
    """Deliver an event to the waiting human gate queue.

    Returns True if the session was in HUMAN_GATE and accepted the event.
    Returns False if no gate is waiting (wrong substate or session not running).
    Called from the WebSocket handler when dispatch_approved or chat arrives.
    """

    queue = _human_gate_queues.get(session_id)
    if queue is None:
        return False
    await queue.put(event_data)
    return True


# ---------------------------------------------------------------------------
# Private: main execution loop
# ---------------------------------------------------------------------------


async def _run_graph(
    session_dir: Path,
    session_id: str,
    data_root: Path,
    manager: ConnectionManager,
) -> None:
    """Main deliberation loop.  Runs nodes in sequence until CONSENSUS or ERROR."""

    try:
        providers_config = _load_providers(data_root)

        while True:
            state = load_state(session_dir)
            session_state = state.get("state")
            substate = state.get("substate")

            # Exit conditions
            if session_state in (
                SessionState.CONSENSUS.value,
                SessionState.COMPLETED.value,
                SessionState.ABANDONED.value,
                SessionState.ERROR.value,
            ):
                logger.info("Session %s exiting loop: state=%s", session_id, session_state)
                break

            if substate is None:
                logger.warning("Session %s has no substate — stopping engine", session_id)
                break

            # Check consensus condition before each moderator turn
            if substate == SessionSubstate.MODERATOR_TURN.value and _all_resolved(state):
                logger.info("All Kanban tasks resolved — triggering CONSENSUS for %s", session_id)
                state["state"] = SessionState.CONSENSUS.value
                state["substate"] = None
                save_state(session_dir, state)
                await manager.broadcast(
                    session_id,
                    {"event": "consensus_triggered", "data": {"reason": "all_tasks_resolved"}},
                )
                break

            # --- MODERATOR_TURN ---
            if substate == SessionSubstate.MODERATOR_TURN.value:
                state = await run_moderator_turn(session_dir, state, manager, providers_config)
                save_state(session_dir, state)
                if state.get("state") == SessionState.ERROR.value:
                    break
                continue

            # --- HUMAN_GATE ---
            if substate == SessionSubstate.HUMAN_GATE.value:
                state = await _wait_human_gate(session_dir, session_id, state, manager)
                save_state(session_dir, state)
                continue

            # --- AGENT_DISPATCH ---
            if substate == SessionSubstate.AGENT_DISPATCH.value:
                state = await run_agent_dispatch(session_dir, state, manager, providers_config)
                save_state(session_dir, state)
                continue

            # --- AGENT_AGGREGATION ---
            if substate == SessionSubstate.AGENT_AGGREGATION.value:
                state = await run_agent_aggregation(session_dir, state, manager)
                save_state(session_dir, state)
                continue

            logger.error("Session %s: unknown substate '%s'", session_id, substate)
            break

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled exception in engine for session %s", session_id)
        try:
            state = load_state(session_dir)
            state["state"] = SessionState.ERROR.value
            state["substate"] = None
            state["error"] = str(exc)
            save_state(session_dir, state)
            await manager.broadcast(
                session_id,
                {"event": "error", "data": {
                    "code": "INTERNAL_ERROR",
                    "message": f"Engine error: {exc}",
                    "recoverable": False,
                }},
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to save ERROR state for session %s", session_id)


async def _wait_human_gate(
    session_dir: Path,
    session_id: str,
    state: dict,
    manager: ConnectionManager,
) -> dict:
    """Register the gate queue and wait for a human event.

    The WebSocket handler calls signal_human_gate() when the user acts.
    """

    queue: asyncio.Queue = asyncio.Queue()
    _human_gate_queues[session_id] = queue

    logger.info("Session %s waiting at HUMAN_GATE", session_id)

    try:
        event = await queue.get()
    finally:
        _human_gate_queues.pop(session_id, None)

    logger.info("Session %s received gate event: type=%s", session_id, event.get("type"))

    state, _next = process_gate_event(state, event)
    return state


def _all_resolved(state: dict) -> bool:
    """Return True if every Kanban task is RESOLVED."""

    tasks = state.get("kanban", {}).get("tasks", [])
    return bool(tasks) and all(t.get("status") == "RESOLVED" for t in tasks)


def _load_providers(data_root: Path) -> dict[str, ProviderConfig]:
    """Load provider configuration from disk."""

    try:
        return load_providers(data_root)
    except FileNotFoundError:
        logger.warning("providers.yaml not found — engine may fail on LLM calls")
        return {}


def _on_task_done(session_id: str, task: asyncio.Task) -> None:
    """Log task completion and clean up."""

    _session_tasks.pop(session_id, None)
    if task.cancelled():
        logger.info("Engine task for session %s was cancelled", session_id)
    elif task.exception():
        logger.error("Engine task for session %s raised: %s", session_id, task.exception())
    else:
        logger.info("Engine task for session %s completed normally", session_id)
