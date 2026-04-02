"""Unit tests for orchestration/engine nodes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.journals import (
    append_turn,
    create_session_dir,
    init_journal,
    read_all_bundles,
    read_journal,
    save_packet,
    save_roll_call,
    save_state,
)
from core.providers.base import CompletionResult, Message, ToolCall
from core.schemas import AgentTurn, KanbanBoard, SessionPacket
from core.schemas.constants import MODERATOR_SUBLOOP_MAX_ITERATIONS
from core.schemas.enums import SessionState, SessionSubstate, TurnType
from orchestration.engine.graph import build_graph
from orchestration.engine.nodes.aggregation import agent_aggregation_node, run_agent_aggregation
from orchestration.engine.nodes.dispatch import agent_dispatch_node, run_agent_dispatch
from orchestration.engine.nodes.human_gate import process_gate_event
from orchestration.engine.nodes.moderator import (
    _run_moderator_subloop,
    moderator_turn_node,
    run_moderator_turn,
)
from orchestration.engine.runner import signal_human_gate, start_session
from orchestration.engine.state import RUNTIME_KEY, EngineStateError
from orchestration.tools.definitions import get_tool_definitions

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
        "is_cycle_one": False,
        "kanban": kanban.model_dump(mode="json"),
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "moderator_messages": [],
        "approved_cards": [],
        "dispatch_results": [],
        "current_bundle_id": "bundle_001",
        "latest_bundle": {"bundle_id": "bundle_001"},
        "moderator_role_id": moderator_id,
        "all_role_ids": [r.role_id for r in packet.roles],
        "non_moderator_role_ids": non_mod_ids,
    }


def _mock_provider(text: str = "Moderator response.", tool_calls: list | None = None):
    """Return a mock ProviderAdapter."""

    class _Mock:
        async def complete(self, messages, model, tools=None, response_format=None, tool_choice=None):
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
# start_session / graph entry
# ---------------------------------------------------------------------------


def test_graph_entry_point_is_agent_aggregation():
    graph = build_graph()
    if getattr(graph, "entry_point", None):
        assert graph.entry_point == "agent_aggregation"
    else:
        graph_obj = graph.get_graph()
        assert graph_obj.entry_point == "agent_aggregation"


@pytest.mark.asyncio
async def test_start_session_dispatches_all_roles_in_parallel(
    tmp_data_root, valid_packet, valid_roll_call
):
    session_id = "sess_test"
    session_dir = create_session_dir(tmp_data_root, valid_packet.project_name, session_id)
    save_packet(session_dir, valid_packet)
    save_roll_call(session_dir, valid_roll_call)

    for role in valid_packet.roles:
        init_journal(session_dir, role.role_id, session_id)

    kanban = KanbanBoard.from_agenda(valid_packet.agenda)
    state = {
        "session_id": session_id,
        "project_name": valid_packet.project_name,
        "packet_id": valid_packet.packet_id,
        "state": SessionState.ACTIVE.value,
        "substate": None,
        "kanban": kanban.model_dump(mode="json"),
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
    }
    save_state(session_dir, state)

    broadcast_fn = AsyncMock()
    providers_config = _mock_providers_config(session_dir, valid_roll_call)

    expected_calls = len(valid_packet.roles)
    started = {"count": 0}
    all_started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingProvider:
        async def complete(self, messages, model, tools=None, response_format=None, tool_choice=None):
            started["count"] += 1
            if started["count"] == expected_calls:
                all_started.set()
            await release.wait()
            return CompletionResult(
                text="init",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _BlockingProvider()
    seen = {}

    class _FakeGraph:
        async def ainvoke(self, state, config=None):
            assert config["entry_point"] == "human_gate"
            seen["substate"] = state.get("substate")
            seen["is_cycle_one"] = state.get("is_cycle_one")
            return state

        def get_graph(self):
            return build_graph().get_graph()

    with (
        patch("orchestration.engine.runner.get_adapter", return_value=provider),
        patch("orchestration.engine.runner.load_providers", return_value=providers_config),
        patch("orchestration.engine.runner.build_graph", return_value=_FakeGraph()),
    ):
        task = asyncio.create_task(start_session(session_id, tmp_data_root, broadcast_fn))
        await all_started.wait()
        state_payload = json.loads((session_dir / "state.json").read_text())
        assert state_payload["substate"] == SessionSubstate.INIT_DISPATCH.value
        release.set()
        await task

    assert started["count"] == expected_calls + 1
    assert seen["substate"] == SessionSubstate.HUMAN_GATE.value
    assert seen["is_cycle_one"] is True

    for role in valid_packet.roles:
        journal = read_journal(session_dir, role.role_id)
        assert len(journal.turns) == 1
        assert journal.turns[0].turn_type == TurnType.INIT

    bundles = read_all_bundles(session_dir)
    assert bundles
    assert bundles[0].bundle_id == "bundle_001"


# ---------------------------------------------------------------------------
# invariants (moderator/dispatch)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderator_turn_raises_without_bundle(tmp_session_dir):
    state = _make_state(tmp_session_dir)
    state["latest_bundle"] = None
    with pytest.raises(EngineStateError):
        await moderator_turn_node(state)


@pytest.mark.asyncio
async def test_agent_dispatch_asserts_approved_cards(tmp_session_dir):
    state = _make_state(tmp_session_dir)
    state["approved_cards"] = []
    with pytest.raises(AssertionError):
        await agent_dispatch_node(state)


@pytest.mark.asyncio
async def test_subloop_two_iterations(tmp_session_dir, valid_roll_call, valid_packet):
    session_id = "sess_test"
    save_roll_call(tmp_session_dir, valid_roll_call)
    state = _make_state(tmp_session_dir, session_id=session_id)
    tools = get_tool_definitions()

    class _Provider:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, model, tools=None, response_format=None):
            self.calls += 1
            if self.calls == 1:
                return CompletionResult(
                    text="Updated kanban.",
                    tool_calls=[
                        ToolCall(
                            name="update_kanban",
                            arguments={
                                "updates": [
                                    {
                                        "question_id": valid_packet.agenda[0].question_id,
                                        "new_status": "AGENT_DELIBERATION",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=1,
                )
            return CompletionResult(
                text="Synthesis complete.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _Provider()
    setattr(provider, "_apical_model", "mock-model")

    final_text, ws_events = await _run_moderator_subloop(
        system_prompt="system",
        conversation_history=[Message(role="user", content="Start")],
        tools=tools,
        provider_adapter=provider,
        session_state=state,
        ws_manager=AsyncMock(),
        session_id=session_id,
    )

    assert provider.calls == 2
    assert final_text == "Synthesis complete."
    assert len(ws_events) == 1
    assert state["kanban"]["tasks"][0]["status"] == "AGENT_DELIBERATION"


@pytest.mark.asyncio
async def test_subloop_three_iterations(tmp_session_dir, valid_roll_call, valid_packet):
    session_id = "sess_test"
    save_roll_call(tmp_session_dir, valid_roll_call)
    state = _make_state(tmp_session_dir, session_id=session_id)
    tools = get_tool_definitions()

    class _Provider:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, model, tools=None, response_format=None):
            self.calls += 1
            if self.calls == 1:
                return CompletionResult(
                    text="Kanban updated.",
                    tool_calls=[
                        ToolCall(
                            name="update_kanban",
                            arguments={
                                "updates": [
                                    {
                                        "question_id": valid_packet.agenda[0].question_id,
                                        "new_status": "AGENT_DELIBERATION",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=1,
                )
            if self.calls == 2:
                return CompletionResult(
                    text="Requesting follow-ups.",
                    tool_calls=[
                        ToolCall(
                            name="generate_action_cards",
                            arguments={
                                "cards": [
                                    {
                                        "target_role_id": "RG-CRIT",
                                        "prompt_text": "Clarify domain boundaries.",
                                        "context_note": "Need critic follow-up.",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=1,
                )
            return CompletionResult(
                text="Final synthesis.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _Provider()
    setattr(provider, "_apical_model", "mock-model")

    final_text, ws_events = await _run_moderator_subloop(
        system_prompt="system",
        conversation_history=[Message(role="user", content="Start")],
        tools=tools,
        provider_adapter=provider,
        session_state=state,
        ws_manager=AsyncMock(),
        session_id=session_id,
    )

    assert provider.calls == 3
    assert final_text == "Final synthesis."
    assert len(ws_events) == 2
    assert len(state["pending_action_cards"]) == 1


@pytest.mark.asyncio
async def test_subloop_cap_exceeded(tmp_session_dir, valid_roll_call, valid_packet):
    session_id = "sess_test"
    save_roll_call(tmp_session_dir, valid_roll_call)
    state = _make_state(tmp_session_dir, session_id=session_id)
    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)

    class _Provider:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, model, tools=None, response_format=None):
            self.calls += 1
            return CompletionResult(
                text="Tooling.",
                tool_calls=[
                    ToolCall(
                        name="update_kanban",
                        arguments={
                            "updates": [
                                {
                                    "question_id": valid_packet.agenda[0].question_id,
                                    "new_status": "AGENT_DELIBERATION",
                                }
                            ]
                        },
                    )
                ],
                usage={},
                finish_reason="tool_calls",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _Provider()

    broadcast_fn = AsyncMock()
    with patch("orchestration.engine.nodes.moderator.get_adapter", return_value=provider):
        await run_moderator_turn(tmp_session_dir, state, broadcast_fn, providers_config)

    assert provider.calls == MODERATOR_SUBLOOP_MAX_ITERATIONS
    failure_text = "Moderator sub-loop exceeded"
    assert any(
        call.args[1]["data"]["text"].startswith(failure_text)
        for call in broadcast_fn.await_args_list
        if call.args and call.args[1]["event"] == "moderator_turn"
    )


@pytest.mark.asyncio
async def test_subloop_ws_events_not_broadcast_mid_loop(
    tmp_session_dir, valid_roll_call, valid_packet
):
    session_id = "sess_test"
    save_roll_call(tmp_session_dir, valid_roll_call)
    state = _make_state(tmp_session_dir, session_id=session_id)
    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)

    broadcast_fn = AsyncMock()

    class _Provider:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, model, tools=None, response_format=None):
            assert broadcast_fn.call_count == 0
            self.calls += 1
            if self.calls == 1:
                return CompletionResult(
                    text="Update kanban.",
                    tool_calls=[
                        ToolCall(
                            name="update_kanban",
                            arguments={
                                "updates": [
                                    {
                                        "question_id": valid_packet.agenda[0].question_id,
                                        "new_status": "AGENT_DELIBERATION",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=1,
                )
            return CompletionResult(
                text="Done.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _Provider()

    with patch("orchestration.engine.nodes.moderator.get_adapter", return_value=provider):
        await run_moderator_turn(tmp_session_dir, state, broadcast_fn, providers_config)

    assert provider.calls == 2


@pytest.mark.asyncio
async def test_subloop_tool_result_appended_to_history(tmp_session_dir, valid_roll_call, valid_packet):
    session_id = "sess_test"
    save_roll_call(tmp_session_dir, valid_roll_call)
    state = _make_state(tmp_session_dir, session_id=session_id)
    tools = get_tool_definitions()

    class _Provider:
        def __init__(self):
            self.calls = 0
            self.second_messages = None

        async def complete(self, messages, model, tools=None, response_format=None):
            self.calls += 1
            if self.calls == 1:
                return CompletionResult(
                    text="First tool call.",
                    tool_calls=[
                        ToolCall(
                            name="update_kanban",
                            arguments={
                                "updates": [
                                    {
                                        "question_id": valid_packet.agenda[0].question_id,
                                        "new_status": "AGENT_DELIBERATION",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=1,
                )
            self.second_messages = messages
            return CompletionResult(
                text="Final response.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _Provider()
    setattr(provider, "_apical_model", "mock-model")

    await _run_moderator_subloop(
        system_prompt="system",
        conversation_history=[Message(role="user", content="Start")],
        tools=tools,
        provider_adapter=provider,
        session_state=state,
        ws_manager=AsyncMock(),
        session_id=session_id,
    )

    assert provider.calls == 2
    assert provider.second_messages is not None
    assert any(
        msg.role == "assistant" and msg.content == "First tool call."
        for msg in provider.second_messages
    )
    assert any(
        msg.role == "user"
        and "Tool result" in msg.content
        and "update_kanban" in msg.content
        for msg in provider.second_messages
    )


@pytest.mark.asyncio
async def test_aggregation_cycle_one_excludes_moderator_init(tmp_session_dir, valid_packet):
    session_id = "sess_test"
    for role in valid_packet.roles:
        init_journal(tmp_session_dir, role.role_id, session_id)
        agent_turn = AgentTurn(
            turn_id=uuid4(),
            session_id=session_id,
            role_id=role.role_id,
            turn_type=TurnType.INIT,
            bundle_id=None,
            prompt_hash="",
            approved_prompt="init",
            agent_response=f"hello from {role.role_id}",
            status="OK",
            error_message=None,
            metadata={"latency_ms": 1},
        )
        append_turn(tmp_session_dir, role.role_id, agent_turn)

    state = _make_state(tmp_session_dir, session_id=session_id)
    state["is_cycle_one"] = True
    state[RUNTIME_KEY] = {"broadcast": AsyncMock(), "data_root": tmp_session_dir}

    result_state = await agent_aggregation_node(state)
    bundles = read_all_bundles(tmp_session_dir)
    assert len(bundles) == 1
    response_roles = {resp.role_id for resp in bundles[0].responses}
    moderator_id = next(r.role_id for r in valid_packet.roles if r.is_moderator)
    assert moderator_id not in response_roles
    assert result_state["is_cycle_one"] is False


@pytest.mark.asyncio
async def test_aggregation_cycle_one_sets_flag_false(tmp_session_dir, valid_packet):
    session_id = "sess_test"
    for role in valid_packet.roles:
        init_journal(tmp_session_dir, role.role_id, session_id)
        agent_turn = AgentTurn(
            turn_id=uuid4(),
            session_id=session_id,
            role_id=role.role_id,
            turn_type=TurnType.INIT,
            bundle_id=None,
            prompt_hash="",
            approved_prompt="init",
            agent_response=f"hello from {role.role_id}",
            status="OK",
            error_message=None,
            metadata={"latency_ms": 1},
        )
        append_turn(tmp_session_dir, role.role_id, agent_turn)

    state = _make_state(tmp_session_dir, session_id=session_id)
    state["is_cycle_one"] = True
    state[RUNTIME_KEY] = {"broadcast": AsyncMock(), "data_root": tmp_session_dir}

    result_state = await agent_aggregation_node(state)
    assert result_state["is_cycle_one"] is False


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

    broadcast_fn = AsyncMock()

    with patch("orchestration.engine.nodes.dispatch.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider("Agent analysis result.")
        result_state = await run_agent_dispatch(
            tmp_session_dir, state, broadcast_fn, providers_config
        )

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

    broadcast_fn = AsyncMock()

    async def _slow_complete(*args, **kwargs):
        await asyncio.sleep(200)  # longer than AGENT_TIMEOUT_SECONDS in test

    slow_provider = MagicMock()
    slow_provider.complete = _slow_complete

    with (
        patch("orchestration.engine.nodes.dispatch.get_adapter", return_value=slow_provider),
        patch("orchestration.engine.nodes.dispatch.AGENT_TIMEOUT_SECONDS", 0.01),
    ):
        result_state = await run_agent_dispatch(
            tmp_session_dir, state, broadcast_fn, providers_config
        )

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

    broadcast_fn = AsyncMock()

    result_state = await run_agent_aggregation(tmp_session_dir, state, broadcast_fn)

    assert result_state["substate"] == SessionSubstate.MODERATOR_TURN.value

    bundles = read_all_bundles(tmp_session_dir)
    assert len(bundles) == 1
    assert bundles[0].bundle_id == "bundle_001"
    assert bundles[0].responses[0].role_id == "RG-CRIT"

    # Moderator messages should have been updated with the bundle text
    mod_msgs = result_state["moderator_messages"]
    assert any("AGENT RESPONSES" in m["content"] for m in mod_msgs if m["role"] == "user")


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

    broadcast_fn = AsyncMock()

    result_state = await run_agent_aggregation(tmp_session_dir, state, broadcast_fn)
    assert result_state["dispatch_results"] == []
    assert result_state["approved_cards"] == []


# ---------------------------------------------------------------------------
# run_moderator_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_moderator_turn_text_response(tmp_session_dir, valid_packet, valid_roll_call):
    """Moderator turn with text-only response updates chat_history and substate."""

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    broadcast_fn = AsyncMock()

    with patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider("Hello from moderator.")
        result_state = await run_moderator_turn(
            tmp_session_dir, state, broadcast_fn, providers_config
        )

    assert result_state["substate"] == SessionSubstate.HUMAN_GATE.value
    chat = result_state["chat_history"]
    assert any(m["content"] == "Hello from moderator." for m in chat)


@pytest.mark.asyncio
async def test_moderator_turn_with_tool_calls(tmp_session_dir, valid_packet, valid_roll_call):
    """Moderator turn with valid tool calls updates pending_action_cards."""

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    broadcast_fn = AsyncMock()

    non_mod_id = state["non_moderator_role_ids"][0]
    class _Provider:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, model, tools=None, response_format=None):
            self.calls += 1
            if self.calls == 1:
                return CompletionResult(
                    text="Drafting cards.",
                    tool_calls=[
                        ToolCall(
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
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=1,
                )
            return CompletionResult(
                text="Here are the action cards.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    with patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _Provider()
        result_state = await run_moderator_turn(
            tmp_session_dir, state, broadcast_fn, providers_config
        )

    assert len(result_state["pending_action_cards"]) == 1
    assert result_state["pending_action_cards"][0]["target_role_id"] == non_mod_id


@pytest.mark.asyncio
async def test_moderator_turn_invalid_tool_call_prompts_correction(tmp_session_dir, valid_roll_call):
    """Malformed tool call triggers a correction prompt in the sub-loop."""

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    broadcast_fn = AsyncMock()

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

    class _Provider:
        def __init__(self):
            self.calls = 0
            self.second_messages = None

        async def complete(self, messages, model, tools=None, response_format=None):
            self.calls += 1
            if self.calls == 1:
                return CompletionResult(
                    text="Trying again.",
                    tool_calls=[bad_tool_call],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=0,
                )
            if self.calls == 2:
                self.second_messages = messages
                return CompletionResult(
                    text="Corrected card.",
                    tool_calls=[
                        ToolCall(
                            name="generate_action_cards",
                            arguments={
                                "cards": [
                                    {
                                        "target_role_id": "RG-CRIT",
                                        "prompt_text": "Clarify domains",
                                        "context_note": "Need critic follow-up",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_calls",
                    latency_ms=0,
                )
            return CompletionResult(
                text="Final response.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=0,
            )

        async def health_check(self):
            return True

    provider = _Provider()
    with patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = provider
        result_state = await run_moderator_turn(
            tmp_session_dir, state, broadcast_fn, providers_config
        )

    assert len(result_state["pending_action_cards"]) == 1
    assert result_state["pending_action_cards"][0]["target_role_id"] == "RG-CRIT"
    assert provider.second_messages is not None
    assert any(
        msg.role == "user"
        and "Your last tool call to 'generate_action_cards' was invalid" in msg.content
        for msg in provider.second_messages
    )


@pytest.mark.asyncio
async def test_moderator_turn_api_failure_sets_error(tmp_session_dir, valid_roll_call):
    """Provider failure after max retries transitions session to ERROR."""

    from core.providers.base import ProviderError

    save_roll_call(tmp_session_dir, valid_roll_call)

    state = _make_state(tmp_session_dir)
    save_state(tmp_session_dir, state)

    providers_config = _mock_providers_config(tmp_session_dir, valid_roll_call)
    broadcast_fn = AsyncMock()

    class _FailingProvider:
        async def complete(self, messages, model, tools=None, response_format=None, tool_choice=None):
            raise ProviderError("mock", 500, "Internal error")

        async def health_check(self):
            return False

    with (
        patch("orchestration.engine.nodes.moderator.get_adapter") as mock_get_adapter,
        patch("orchestration.engine.nodes.moderator.MODERATOR_RETRY_BACKOFF", [0, 0, 0]),
    ):
        mock_get_adapter.return_value = _FailingProvider()
        result_state = await run_moderator_turn(
            tmp_session_dir, state, broadcast_fn, providers_config
        )

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
