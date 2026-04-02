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
from core.schemas.constants import MODERATOR_RETRY_BACKOFF, MODERATOR_RETRY_MAX, TOOL_CALL_RETRY_MAX
from core.schemas.enums import ErrorCode, SessionState, SessionSubstate, TurnType
from orchestration.engine.state import RUNTIME_KEY, EngineStateError, strip_runtime
from orchestration.tools.definitions import get_tool_definitions
from orchestration.tools.handlers import handle_tool_call
from orchestration.tools.validation import validate_tool_call

logger = logging.getLogger(__name__)


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
    approved_prompt = next(
        (msg["content"] for msg in reversed(moderator_messages) if msg["role"] == "user"),
        "",
    )

    # Call the provider with backoff on errors
    result = await _call_with_backoff(adapter, messages, model, system_prompt, tools, session_id)

    if result is None:
        # All retries exhausted — transition to ERROR
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

    latest_bundle = state.get("latest_bundle")
    bundle_id = latest_bundle.get("bundle_id") if isinstance(latest_bundle, dict) else None
    moderator_turn = AgentTurn(
        turn_id=uuid4(),
        session_id=session_id,
        role_id=moderator_role.role_id,
        turn_type=TurnType.DELIBERATION,
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
        },
    )
    append_turn(session_dir, moderator_role.role_id, moderator_turn)

    tool_calls = list(result.tool_calls)
    if not tool_calls:
        follow_up_prompt = (
            "You must now call tools. Use update_kanban to reflect current progress and "
            "generate_action_cards for the next agent prompts. If a decision point is ready, "
            "use generate_decision_quiz. Respond with tool calls only; no additional text."
        )
        follow_up_messages = [
            *messages,
            Message(role="assistant", content=result.text or ""),
            Message(role="user", content=follow_up_prompt),
        ]
        follow_up_result = await _call_once(
            adapter,
            follow_up_messages,
            model,
            system_prompt,
            tools,
            tool_choice="required",
        )
        if follow_up_result is not None and follow_up_result.tool_calls:
            tool_calls = list(follow_up_result.tool_calls)

    # Store the moderator's text in chat_history
    if result.text:
        state.setdefault("chat_history", []).append({"role": "moderator", "content": result.text})
        await broadcast_fn(
            session_id,
            {"event": "moderator_turn", "data": {"text": result.text}},
        )

    # Update moderator conversation history
    moderator_messages.append({"role": "assistant", "content": result.text or ""})

    # Process tool calls (with per-tool correction attempts on validation failure)
    # Keep tool_messages as plain dicts throughout for consistent subscripting
    tool_messages = [{"role": m.role, "content": m.content} for m in messages]
    tool_messages.append({"role": "assistant", "content": result.text or ""})

    for tool_call in tool_calls:
        errors = validate_tool_call(tool_call.name, tool_call.arguments, state)

        attempt_count = 0
        while errors and attempt_count < TOOL_CALL_RETRY_MAX:
            logger.warning(
                "Tool call '%s' invalid (attempt %d): %s",
                tool_call.name,
                attempt_count + 1,
                errors,
            )
            attempt_prompt = _build_tool_call_correction_prompt(
                tool_call.name,
                tool_call.arguments,
                errors,
            )

            tool_messages_objs = [
                Message(role=m["role"], content=m["content"]) for m in tool_messages
            ]
            attempt_msg = Message(role="user", content=attempt_prompt)
            tool_messages_objs.append(attempt_msg)
            tool_messages.append({"role": "user", "content": attempt_prompt})

            attempt_result = await _call_once(
                adapter,
                tool_messages_objs,
                model,
                system_prompt,
                tools,
            )
            if attempt_result is None:
                errors = ["Provider error during tool correction attempt"]
                break

            tool_call = attempt_result.tool_calls[0] if attempt_result.tool_calls else tool_call
            errors = (
                validate_tool_call(tool_call.name, tool_call.arguments, state)
                if attempt_result.tool_calls
                else []
            )
            tool_messages.append({"role": "assistant", "content": attempt_result.text or ""})
            attempt_count += 1

        if errors:
            # Max retries exhausted — notify human
            logger.warning(
                "Dropping tool call '%s' after %d attempts",
                tool_call.name,
                attempt_count,
            )
            await broadcast_fn(
                session_id,
                {"event": "tool_call_dropped", "data": {"tool": tool_call.name, "errors": errors}},
            )
            continue

        tool_result = handle_tool_call(tool_call.name, tool_call.arguments, state)
        for ws_event in tool_result.ws_events:
            await broadcast_fn(session_id, ws_event)

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
        result = await _call_once(adapter, messages, model, system_prompt, tools)
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
    tool_choice: str | dict | None = None,
) -> object | None:
    """Attempt a single provider call. Returns None on ProviderError."""

    try:
        system_msg = Message(role="system", content=system_prompt)
        full_messages = [system_msg] + list(messages)
        return await adapter.complete(full_messages, model, tools=tools, tool_choice=tool_choice)
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
