"""MODERATOR_TURN node — calls the Moderator LLM and processes tool calls (§4.4.2)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from core.config import ProviderConfig, load_providers, resolve_api_key
from core.journals import append_turn, save_state
from core.prompt_assembly.moderator_prompt import assemble_moderator_prompt
from core.providers.base import Message, ProviderAdapter, ProviderError
from core.providers.factory import get_adapter
from core.schemas import AgentTurn, RollCall, SessionPacket
from core.schemas.constants import (
    MODERATOR_RETRY_BACKOFF,
    MODERATOR_RETRY_MAX,
    MODERATOR_SUBLOOP_MAX_ITERATIONS,
)
from core.schemas.enums import ErrorCode, SessionState, SessionSubstate, TurnType
from orchestration.engine.state import RUNTIME_KEY, EngineStateError, strip_runtime
from orchestration.tools.definitions import get_tool_definitions
from orchestration.tools.handlers import handle_tool_call
from orchestration.tools.validation import validate_tool_call, validate_tool_semantics

logger = logging.getLogger(__name__)


async def _run_moderator_subloop(
    system_prompt: str,
    conversation_history: list[Message],
    tools: list,
    provider_adapter: ProviderAdapter,
    session_state: dict,
    ws_manager: Callable[[str, dict], Awaitable[None]],
    session_id: str,
) -> tuple[str, list[dict]]:
    """Run the moderator sub-loop within a single moderator turn."""

    model = getattr(provider_adapter, "_apical_model", None)
    if not model:
        session_state["_moderator_subloop_provider_error"] = True
        return "", []

    subloop_messages = list(conversation_history)
    accumulated_events: list[dict] = []
    latest_bundle = session_state.get("latest_bundle")
    bundle_id = latest_bundle.get("bundle_id") if isinstance(latest_bundle, dict) else None
    session_dir = Path(session_state["session_dir"])

    for iteration in range(1, MODERATOR_SUBLOOP_MAX_ITERATIONS + 1):
        approved_prompt = next(
            (msg.content for msg in reversed(subloop_messages) if msg.role == "user"),
            "",
        )
        result = await _call_with_backoff(
            provider_adapter,
            subloop_messages,
            model,
            system_prompt,
            tools,
            session_id,
        )
        if result is None:
            session_state["_moderator_subloop_provider_error"] = True
            return "", []

        moderator_turn = AgentTurn(
            turn_id=uuid4(),
            session_id=session_id,
            role_id=session_state.get("moderator_role_id", ""),
            turn_type=TurnType.MODERATOR_SUBLOOP,
            bundle_id=bundle_id,
            prompt_hash="",
            approved_prompt=approved_prompt,
            agent_response=result.text or "",
            status="OK",
            error_message=None,
            metadata={
                **result.usage,
                "latency_ms": result.latency_ms,
                "finish_reason": result.finish_reason,
                "iteration": iteration,
            },
        )
        append_turn(session_dir, session_state.get("moderator_role_id", ""), moderator_turn)

        assistant_text = result.text or ""
        subloop_messages.append(Message(role="assistant", content=assistant_text))

        if not result.tool_calls:
            return assistant_text, accumulated_events

        correction_needed = False
        for tool_call in result.tool_calls:
            errors = validate_tool_call(tool_call.name, tool_call.arguments, session_state)
            errors.extend(validate_tool_semantics(tool_call.name, tool_call.arguments, session_state))
            if errors:
                correction_prompt = _build_tool_call_correction_prompt(
                    tool_call.name, tool_call.arguments, errors
                )
                subloop_messages.append(Message(role="user", content=correction_prompt))
                correction_needed = True
                break

            tool_result = handle_tool_call(tool_call.name, tool_call.arguments, session_state)
            accumulated_events.extend(tool_result.ws_events)
            subloop_messages.append(
                Message(
                    role="user",
                    content=_format_tool_result_message(
                        tool_call.name,
                        tool_call.arguments,
                        tool_result,
                    ),
                )
            )

        if correction_needed:
            continue

    session_state["_moderator_subloop_failed"] = True
    return "", []




async def run_moderator_turn(
    session_dir: Path,
    state: dict,
    broadcast_fn: Callable[[str, dict], Awaitable[None]],
    providers_config: dict[str, ProviderConfig],
) -> dict:
    """Run one Moderator LLM turn: assemble context, call provider, execute tools.

    Modifies state in-place and returns it.  The runner saves state to disk
    after this function returns.

    On unrecoverable provider failure (after MODERATOR_RETRY_MAX retries) the
    session state is set to ERROR and the updated state is returned.
    """

    if not state.get("latest_bundle"):
        raise EngineStateError(
            "moderator_turn_node entered without a bundle in state. "
            "This is a graph routing bug. Check graph entry point and aggregation output."
        )

    session_id = state["session_id"]
    packet = _load_packet(session_dir)
    roll_call = _load_roll_call(session_dir)

    moderator_role = next(r for r in packet.roles if r.is_moderator)
    moderator_assignment = next(
        a for a in roll_call.assignments if a.role_id == moderator_role.role_id
    )
    provider_cfg = providers_config[moderator_assignment.provider]
    adapter = _make_adapter(moderator_assignment.provider, provider_cfg)
    model = moderator_assignment.model
    base_url = getattr(adapter, "base_url", "")
    logger.info(
        "Moderator call: provider=%s, model=%s, base_url=%s",
        moderator_assignment.provider,
        model,
        base_url,
    )

    # Enrich state with role context for tool validation
    state.setdefault("moderator_role_id", moderator_role.role_id)
    state.setdefault("all_role_ids", [r.role_id for r in packet.roles])
    state.setdefault(
        "non_moderator_role_ids",
        [r.role_id for r in packet.roles if not r.is_moderator],
    )

    # Build the moderator system prompt
    tools = get_tool_definitions()
    tool_defs_text = _format_tool_definitions(tools)
    kanban_state_text = _format_kanban(state.get("kanban", {}))
    system_prompt = assemble_moderator_prompt(
        packet=packet,
        role=moderator_role,
        non_moderator_role_ids=state["non_moderator_role_ids"],
        tool_definitions_text=tool_defs_text,
        kanban_state=kanban_state_text,
    )

    # Build the messages list for this turn
    moderator_messages = list(state.get("moderator_messages", []))
    if not moderator_messages:
        moderator_messages = [{"role": "user", "content": "Begin deliberation."}]

    # Append any queued human messages as extra user content before the LLM call
    queued = state.get("queued_human_messages", [])
    if queued and moderator_messages:
        queued_text = "\n".join(f"[Human]: {m}" for m in queued)
        # Append to the last user message or add a new one
        if moderator_messages[-1]["role"] == "user":
            moderator_messages[-1] = {
                "role": "user",
                "content": moderator_messages[-1]["content"] + f"\n\n{queued_text}",
            }
        else:
            moderator_messages.append({"role": "user", "content": queued_text})

    messages = [Message(role=m["role"], content=m["content"]) for m in moderator_messages]

    setattr(adapter, "_apical_model", model)
    final_text, ws_events = await _run_moderator_subloop(
        system_prompt=system_prompt,
        conversation_history=messages,
        tools=tools,
        provider_adapter=adapter,
        session_state=state,
        ws_manager=broadcast_fn,
        session_id=session_id,
    )

    if state.pop("_moderator_subloop_provider_error", False):
        logger.error(
            "Moderator API failed after %d retries for session %s",
            MODERATOR_RETRY_MAX,
            session_id,
        )
        state["state"] = SessionState.ERROR.value
        state["substate"] = None
        state["error"] = "Moderator API failed after maximum retries"
        await broadcast_fn(
            session_id,
            {
                "event": "error",
                "data": {
                    "code": ErrorCode.PROVIDER_ERROR.value,
                    "message": "Moderator failed after maximum retries",
                    "recoverable": False,
                },
            },
        )
        return state

    if state.pop("_moderator_subloop_failed", False):
        failure_message = (
            "Moderator sub-loop exceeded "
            f"{MODERATOR_SUBLOOP_MAX_ITERATIONS} iterations without a final text response. "
            "Please retry or switch the moderator model."
        )
        state.setdefault("chat_history", []).append(
            {"role": "system", "content": failure_message}
        )
        await broadcast_fn(
            session_id,
            {"event": "moderator_turn", "data": {"text": failure_message}},
        )
    else:
        for ws_event in ws_events:
            await broadcast_fn(session_id, ws_event)

        if final_text:
            state.setdefault("chat_history", []).append(
                {"role": "moderator", "content": final_text}
            )
            await broadcast_fn(
                session_id,
                {"event": "moderator_turn", "data": {"text": final_text}},
            )
            moderator_messages.append({"role": "assistant", "content": final_text})

    # Move queued human messages to chat history (now consumed)
    if queued:
        for msg in queued:
            state["chat_history"].append({"role": "human", "content": msg})
        state["queued_human_messages"] = []

    state["moderator_messages"] = moderator_messages
    state["substate"] = SessionSubstate.HUMAN_GATE.value

    # Broadcast full state sync so client reflects new kanban/cards/quizzes
    await broadcast_fn(
        session_id,
        {
            "event": "state_sync",
            "data": {
                "kanban": state.get("kanban"),
                "pending_actions": state.get("pending_action_cards", []),
                "pending_quizzes": state.get("pending_quizzes", []),
                "chat_history": state.get("chat_history", []),
                "session_state": state.get("state"),
                "substate": state.get("substate"),
            },
        },
    )

    return state


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _call_with_backoff(
    adapter: ProviderAdapter,
    messages: list[Message],
    model: str,
    system_prompt: str,
    tools: list,
    session_id: str,
) -> object | None:
    """Call the provider with exponential backoff on failure.

    Returns CompletionResult on success, None after MODERATOR_RETRY_MAX failures.
    """

    for attempt in range(MODERATOR_RETRY_MAX):
        result = await _call_once(
            adapter,
            messages,
            model,
            system_prompt,
            tools,
        )
        if result is not None:
            return result
        if attempt < MODERATOR_RETRY_MAX - 1:
            wait = MODERATOR_RETRY_BACKOFF[attempt]
            logger.warning(
                "Moderator call failed (attempt %d), next attempt in %ds",
                attempt + 1,
                wait,
            )
            await asyncio.sleep(wait)
        else:
            logger.error("Moderator call failed after %d attempts", MODERATOR_RETRY_MAX)
    return None


async def _call_once(
    adapter: ProviderAdapter,
    messages: list[Message],
    model: str,
    system_prompt: str,
    tools: list,
) -> object | None:
    """Attempt a single provider call. Returns None on ProviderError."""

    try:
        system_msg = Message(role="system", content=system_prompt)
        full_messages = [system_msg] + list(messages)
        return await adapter.complete(full_messages, model, tools=tools)
    except ProviderError as exc:
        if exc.status_code == 400:
            logger.error(
                "Provider %s returned 400 for model %s: %s",
                exc.provider,
                exc.model,
                exc.response_body,
            )
        else:
            logger.warning("ProviderError: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error calling provider: %s", exc)
        return None


def _make_adapter(provider_key: str, cfg: ProviderConfig) -> ProviderAdapter:
    """Resolve API key and construct provider adapter."""

    api_key = resolve_api_key(cfg)
    import copy

    resolved = copy.copy(cfg)
    resolved = cfg.model_copy(update={"api_key": api_key})
    return get_adapter(provider_key, resolved)


def _load_packet(session_dir: Path) -> SessionPacket:
    from core.journals.session_dir import load_packet

    return load_packet(session_dir)


def _load_roll_call(session_dir: Path) -> RollCall:
    from core.journals.session_dir import load_roll_call

    return load_roll_call(session_dir)


def _format_tool_definitions(tools: list) -> str:
    """Render tool definitions as JSON for the system prompt."""

    import json

    return json.dumps(
        [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools],
        indent=2,
    )


def _build_tool_call_correction_prompt(
    tool_name: str,
    arguments: dict,
    errors: list[str],
) -> str:
    """Return a correction prompt for an invalid tool call."""

    import json

    args_str = json.dumps(arguments, indent=2, default=str)
    errors_str = "\n".join(f"- {error}" for error in errors)
    return (
        f"Your last tool call to '{tool_name}' was invalid. "
        "Please correct the parameters and submit a new tool call.\n\n"
        f"Invalid arguments:\n{args_str}\n\n"
        f"Errors:\n{errors_str}"
    )


def _format_tool_result_message(tool_name: str, arguments: dict, tool_result: object) -> str:
    """Serialize tool execution results for inclusion in sub-loop context."""

    import json

    args_str = json.dumps(arguments, indent=2, default=str)
    return (
        "Tool result:\n"
        f"tool: {tool_name}\n"
        f"arguments: {args_str}\n"
        f"success: {getattr(tool_result, 'success', False)}\n"
        f"message: {getattr(tool_result, 'message', '')}"
    )


def _format_kanban(kanban: dict) -> str:
    """Render kanban board as a human-readable table."""

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


# LangGraph-compatible stub for graph.py topology definition
async def moderator_turn_node(state: dict) -> dict:
    """LangGraph node: execute moderator turn using runtime dependencies."""

    if not state.get("latest_bundle"):
        raise EngineStateError(
            "moderator_turn_node entered without a bundle in state. "
            "This is a graph routing bug. Check graph entry point and aggregation output."
        )

    runtime = state.get(RUNTIME_KEY, {})
    broadcast_fn = runtime.get("broadcast") or _noop_broadcast
    data_root = runtime.get("data_root")

    session_dir = Path(state["session_dir"])
    providers_config = runtime.get("providers_config")
    if providers_config is None:
        if data_root is None:
            raise EngineStateError("moderator_turn_node missing data_root for provider lookup.")
        providers_config = load_providers(Path(data_root))

    updated_state = await run_moderator_turn(session_dir, state, broadcast_fn, providers_config)
    save_state(session_dir, strip_runtime(updated_state))
    return updated_state


async def _noop_broadcast(session_id: str, event: dict) -> None:
    return None
