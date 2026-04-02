"""Unit tests for orchestration/engine nodes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.journals import (
    init_journal,
    read_all_bundles,
    read_journal,
    save_state,
)
from core.providers.base import CompletionResult, ToolCall
from core.schemas import KanbanBoard, SessionPacket
from core.schemas.enums import SessionState, SessionSubstate
from orchestration.engine.nodes.aggregation import run_agent_aggregation
from orchestration.engine.nodes.dispatch import run_agent_dispatch
from orchestration.engine.nodes.human_gate import process_gate_event
from orchestration.engine.nodes.moderator import run_moderator_turn
from orchestration.engine.runner import signal_human_gate

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_state(session_dir: Path, session_id: str = "sess_test") -> dict:
    """Return a minimal valid state dict for a session in MODERATOR_TURN.

    Also initialises journals for all roles (mirrors sessions.py init flow).
    """

    packet_path = Path(__file__).parent.parent / "fixtures" / "valid_packet.json"
    packet = SessionPacket.model_validate(json.loads(packet_path.read_text()))
    kanban = KanbanBoard.from_agenda(packet.agenda)
    moderator_id = next(r.role_id for r in packet.roles if r.is_moderator)
    non_mod_ids = [r.role_id for r in packet.roles if not r.is_moderator]

    for role in packet.roles:
        journal_path = session_dir / "journals" / f"{role.role_id}_journal.json"
        if not journal_path.exists():
            init_journal(session_dir, role.role_id, session_id)

    return {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "state": SessionState.ACTIVE.value,
        "substate": SessionSubstate.MODERATOR_TURN.value,
        "kanban": kanban.model_dump(mode="json"),
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "moderator_messages": [],
        "approved_cards": [],
        "dispatch_results": [],
        "moderator_role_id": moderator_id,
        "all_role_ids": [r.role_id for r in packet.roles],
        "non_moderator_role_ids": non_mod_ids,
    }


def _mock_provider(text: str = "Moderator response.", tool_calls: list | None = None):
    """Return a mock ProviderAdapter."""

    class _Mock:
        async def complete(self, messages, model, tools=None, response_format=None):
            return CompletionResult(
                text=text,
                tool_calls=tool_calls or [],
                usage={},
                finish_reason="stop",
                latency_ms=10,
            )

        async def health_check(self):
            return True

    return _Mock()


def _mock_providers_config(session_dir: Path, valid_roll_call) -> dict:
    """Return a providers_config dict that has all providers from the roll call."""

    from core.config import ProviderConfig

    dummy_cfg = ProviderConfig(
        display_name="Mock",
        base_url="http://mock",
        api_key_env=None,
        api_key="mock-key",
        default_model="mock-model",
        available_models=["mock-model"],
        supports_function_calling=True,
        supports_structured_output=False,
        max_context_tokens=32000,
    )
    providers = {}
    for assignment in valid_roll_call.assignments:
        providers[assignment.provider] = dummy_cfg
    return providers


# ---------------------------------------------------------------------------
# process_gate_event (human_gate)
# ---------------------------------------------------------------------------


def test_process_gate_chat_message_routes_to_moderator():
    state = {
        "session_id": "s",
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "approved_cards": [],
        "substate": "HUMAN_GATE",
    }
    updated, next_sub = process_gate_event(state, {"type": "chat_message", "content": "Hello!"})
    assert next_sub == "MODERATOR_TURN"
    assert "Hello!" in updated["queued_human_messages"]


def test_process_gate_dispatch_approved_with_approved_card():
    card_id = str(uuid4())
    state = {
        "session_id": "s",
        "pending_action_cards": [
            {
                "card_id": card_id,
                "target_role_id": "RG-CRIT",
                "prompt_text": "Analyse",
                "context_note": "Note",
                "status": "PENDING",
            }
        ],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "approved_cards": [],
        "substate": "HUMAN_GATE",
    }
    event = {
        "type": "dispatch_approved",
        "card_resolutions": [{"card_id": card_id, "action": "APPROVED"}],
        "quiz_answers": [],
    }
    updated, next_sub = process_gate_event(state, event)
    assert next_sub == "AGENT_DISPATCH"
    assert len(updated["approved_cards"]) == 1
    assert updated["approved_cards"][0]["status"] == "APPROVED"


def test_process_gate_all_denied_routes_to_moderator():
    card_id = str(uuid4())
    state = {
        "session_id": "s",
        "pending_action_cards": [
            {
                "card_id": card_id,
                "target_role_id": "RG-CRIT",
                "prompt_text": "P",
                "context_note": "N",
                "status": "PENDING",
            }
        ],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "approved_cards": [],
        "substate": "HUMAN_GATE",
    }
    event = {
        "type": "dispatch_approved",
        "card_resolutions": [
            {"card_id": card_id, "action": "DENIED", "denial_reason": "Off topic"}
        ],
        "quiz_answers": [],
    }
    updated, next_sub = process_gate_event(state, event)
    assert next_sub == "MODERATOR_TURN"
    assert not updated["approved_cards"]


def test_process_gate_modified_card():
    card_id = str(uuid4())
    state = {
        "session_id": "s",
        "pending_action_cards": [
            {
                "card_id": card_id,
                "target_role_id": "RG-CRIT",
                "prompt_text": "Original",
                "context_note": "N",
                "status": "PENDING",
            }
        ],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "approved_cards": [],
        "substate": "HUMAN_GATE",
    }
    event = {
        "type": "dispatch_approved",
        "card_resolutions": [
            {"card_id": card_id, "action": "MODIFIED", "modified_prompt": "Edited prompt"}
        ],
        "quiz_answers": [],
    }
    updated, next_sub = process_gate_event(state, event)
    assert next_sub == "AGENT_DISPATCH"
    card = updated["approved_cards"][0]
    assert card["status"] == "MODIFIED"
    assert card["human_modified_prompt"] == "Edited prompt"


# ---------------------------------------------------------------------------
# run_agent_dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_node_writes_journals(tmp_session_dir, valid_packet, valid_roll_call):
    """Dispatch with mocked providers writes journal entries."""

    from core.journals import save_roll_call

    save_roll_call(tmp_session_dir, valid_roll_call)

    non_mod_roles = [r for r in valid_packet.roles if not r.is_moderator]
    target_role = non_mod_roles[0]

    state = _make_state(tmp_session_dir)
    state["approved_cards"] = [
        {
            "card_id": str(uuid4()),
            "target_role_id": target_role.role_id,
            "prompt_text": "Analyse the domains.",
            "context_note": "Need input",
            "status": "APPROVED",
        }
    ]
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)

    manager = MagicMock()
    manager.broadcast = AsyncMock()

    with patch("orchestration.engine.nodes.dispatch.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider("Agent analysis result.")
        result_state = await run_agent_dispatch(tmp_session_dir, state, manager, providers_config)

    assert result_state["substate"] == SessionSubstate.AGENT_AGGREGATION.value
    assert len(result_state["dispatch_results"]) == 1
    assert result_state["dispatch_results"][0]["status"] == "OK"
    assert result_state["dispatch_results"][0]["response_text"] == "Agent analysis result."

    # Verify journal was written
    journal = read_journal(tmp_session_dir, target_role.role_id)
    assert len(journal.turns) == 1
    assert journal.turns[0].approved_prompt == "Analyse the domains."


@pytest.mark.asyncio
async def test_dispatch_node_timeout_captured(tmp_session_dir, valid_packet, valid_roll_call):
    """Timed-out agent call produces TIMEOUT status in dispatch_results."""

    from core.journals import save_roll_call

    save_roll_call(tmp_session_dir, valid_roll_call)

    non_mod_roles = [r for r in valid_packet.roles if not r.is_moderator]
    target_role = non_mod_roles[0]

    state = _make_state(tmp_session_dir)
    state["approved_cards"] = [
        {
            "card_id": str(uuid4()),
            "target_role_id": target_role.role_id,
            "prompt_text": "Slow prompt.",
            "context_note": "Note",
            "status": "APPROVED",
        }
    ]

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)

    manager = MagicMock()
    manager.broadcast = AsyncMock()

    async def _slow_complete(*args, **kwargs):
        await asyncio.sleep(200)  # longer than AGENT_TIMEOUT_SECONDS in test

    slow_provider = MagicMock()
    slow_provider.complete = _slow_complete

    with (
        patch("orchestration.engine.nodes.dispatch.get_adapter", return_value=slow_provider),
        patch("orchestration.engine.nodes.dispatch.AGENT_TIMEOUT_SECONDS", 0.01),
    ):
        result_state = await run_agent_dispatch(tmp_session_dir, state, manager, providers_config)

    assert result_state["dispatch_results"][0]["status"] == "TIMEOUT"


# ---------------------------------------------------------------------------
# run_agent_aggregation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregation_node_writes_bundle(tmp_session_dir, valid_packet):
    """Aggregation node writes bundle to disk and updates moderator_messages."""

    turn_id = str(uuid4())
    state = _make_state(tmp_session_dir)
    state["current_bundle_id"] = "bundle_001"
    state["dispatch_results"] = [
        {
            "role_id": "RG-CRIT",
            "turn_id": turn_id,
            "response_text": "Critic response.",
            "status": "OK",
            "error_message": None,
            "latency_ms": 200,
        }
    ]

    manager = MagicMock()
    manager.broadcast = AsyncMock()

    result_state = await run_agent_aggregation(tmp_session_dir, state, manager)

    assert result_state["substate"] == SessionSubstate.MODERATOR_TURN.value

    bundles = read_all_bundles(tmp_session_dir)
    assert len(bundles) == 1
    assert bundles[0].bundle_id == "bundle_001"
    assert bundles[0].responses[0].role_id == "RG-CRIT"

    # Moderator messages should have been updated with the bundle text
    mod_msgs = result_state["moderator_messages"]
    assert any("bundle_001" in m["content"] for m in mod_msgs if m["role"] == "user")


@pytest.mark.asyncio
async def test_aggregation_clears_dispatch_state(tmp_session_dir):
    """After aggregation, dispatch_results and approved_cards are cleared."""

    state = _make_state(tmp_session_dir)
    state["current_bundle_id"] = "bundle_001"
    state["dispatch_results"] = [
        {
            "role_id": "RG-CRIT",
            "turn_id": str(uuid4()),
            "response_text": "R",
            "status": "OK",
            "error_message": None,
            "latency_ms": 0,
        }
    ]
    state["approved_cards"] = [{"card_id": str(uuid4()), "status": "APPROVED"}]

    manager = MagicMock()
    manager.broadcast = AsyncMock()

    result_state = await run_agent_aggregation(tmp_session_dir, state, manager)
    assert result_state["dispatch_results"] == []
    assert result_state["approved_cards"] == []


# ---------------------------------------------------------------------------
# run_moderator_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderator_turn_text_response(tmp_session_dir, valid_packet, valid_roll_call):
    """Moderator turn with text-only response updates chat_history and substate."""

    from core.journals import save_roll_call

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    with patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider("Hello from moderator.")
        result_state = await run_moderator_turn(tmp_session_dir, state, manager, providers_config)

    assert result_state["substate"] == SessionSubstate.HUMAN_GATE.value
    chat = result_state["chat_history"]
    assert any(m["content"] == "Hello from moderator." for m in chat)


@pytest.mark.asyncio
async def test_moderator_turn_with_tool_calls(tmp_session_dir, valid_packet, valid_roll_call):
    """Moderator turn with valid tool calls updates pending_action_cards."""

    from core.journals import save_roll_call

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    non_mod_id = state["non_moderator_role_ids"][0]
    tool_call = ToolCall(
        name="generate_action_cards",
        arguments={
            "cards": [
                {
                    "target_role_id": non_mod_id,
                    "prompt_text": "Analyse domains",
                    "context_note": "First round",
                }
            ]
        },
    )

    with patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider("Here are the action cards.", [tool_call])
        result_state = await run_moderator_turn(tmp_session_dir, state, manager, providers_config)

    assert len(result_state["pending_action_cards"]) == 1
    assert result_state["pending_action_cards"][0]["target_role_id"] == non_mod_id


@pytest.mark.asyncio
async def test_moderator_turn_invalid_tool_call_retries(tmp_session_dir, valid_roll_call):
    """Malformed tool call triggers retry prompt (up to TOOL_CALL_RETRY_MAX)."""

    from core.journals import save_roll_call

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    # Tool call targets the moderator — always invalid
    bad_tool_call = ToolCall(
        name="generate_action_cards",
        arguments={
            "cards": [
                {
                    "target_role_id": state["moderator_role_id"],  # invalid!
                    "prompt_text": "P",
                    "context_note": "N",
                }
            ]
        },
    )

    call_count = 0

    class _CountingProvider:
        async def complete(self, messages, model, tools=None, response_format=None):
            nonlocal call_count
            call_count += 1
            return CompletionResult(
                text="Trying again.",
                tool_calls=[bad_tool_call],
                usage={},
                finish_reason="stop",
                latency_ms=0,
            )

        async def health_check(self):
            return True

    with patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _CountingProvider()
        result_state = await run_moderator_turn(tmp_session_dir, state, manager, providers_config)

    # 1 initial call + up to TOOL_CALL_RETRY_MAX retries — card should be dropped
    assert len(result_state["pending_action_cards"]) == 0
    # tool_call_dropped event should have been broadcast
    calls = [call[0][1] for call in manager.broadcast.call_args_list]
    assert any(e.get("event") == "tool_call_dropped" for e in calls)


@pytest.mark.asyncio
async def test_moderator_turn_api_failure_sets_error(tmp_session_dir, valid_roll_call):
    """Provider failure after max retries transitions session to ERROR."""

    from core.journals import save_roll_call
    from core.providers.base import ProviderError

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    class _FailingProvider:
        async def complete(self, messages, model, tools=None, response_format=None):
            raise ProviderError("mock", 500, "Internal error")

        async def health_check(self):
            return False

    with (
        patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter,
        patch("orchestration.engine.nodes.moderator.MODERATOR_RETRY_BACKOFF", [0, 0, 0]),
    ):
        mock_get_adapter.return_value = _FailingProvider()
        result_state = await run_moderator_turn(tmp_session_dir, state, manager, providers_config)

    assert result_state["state"] == SessionState.ERROR.value


# ---------------------------------------------------------------------------
# signal_human_gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signal_human_gate_returns_false_when_no_queue():
    delivered = await signal_human_gate("nonexistent_session", {"type": "chat_message"})
    assert delivered is False


@pytest.mark.asyncio
async def test_signal_human_gate_delivers_event():
    from orchestration.engine.runner import _human_gate_queues

    q: asyncio.Queue = asyncio.Queue()
    _human_gate_queues["sess_signal_test"] = q

    try:
        event = {"type": "dispatch_approved", "card_resolutions": []}
        delivered = await signal_human_gate("sess_signal_test", event)
        assert delivered is True
        received = await q.get()
        assert received == event
    finally:
        _human_gate_queues.pop("sess_signal_test", None)
