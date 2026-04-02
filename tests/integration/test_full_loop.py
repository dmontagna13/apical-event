"""Integration test for full cycle-1 flow with mocked providers."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from core.config import ProviderConfig
from core.journals import (
    create_session_dir,
    init_journal,
    read_all_bundles,
    read_journal,
    save_packet,
    save_roll_call,
    save_state,
)
from core.providers.base import CompletionResult, ToolCall
from core.schemas import KanbanBoard
from core.schemas.enums import SessionState, SessionSubstate, TurnType
from orchestration.engine.nodes.aggregation import agent_aggregation_node
from orchestration.engine.nodes.dispatch import run_agent_dispatch
from orchestration.engine.nodes.human_gate import process_gate_event
from orchestration.engine.nodes.moderator import run_moderator_turn
from orchestration.engine.runner import start_session
from orchestration.engine.state import RUNTIME_KEY, strip_runtime


@pytest.mark.asyncio
async def test_full_cycle_one_flow(tmp_data_root, valid_packet, valid_roll_call):
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
    non_mod_roles = [r.role_id for r in valid_packet.roles if not r.is_moderator]

    init_phase = {"active": True}
    started = {"count": 0}
    all_started = asyncio.Event()
    release_init = asyncio.Event()

    class _ScriptedProvider:
        async def complete(self, messages, model, tools=None, response_format=None):
            if tools:
                tool_call = ToolCall(
                    name="generate_action_cards",
                    arguments={
                        "cards": [
                            {
                                "target_role_id": non_mod_roles[0],
                                "prompt_text": "Analyse the domain boundaries.",
                                "context_note": "Kick off deliberation",
                            }
                        ]
                    },
                )
                return CompletionResult(
                    text="Moderator synthesis.",
                    tool_calls=[tool_call],
                    usage={},
                    finish_reason="stop",
                    latency_ms=1,
                )

            if init_phase["active"]:
                started["count"] += 1
                if started["count"] == len(valid_packet.roles):
                    all_started.set()
                await release_init.wait()

            return CompletionResult(
                text="Agent response.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

        async def health_check(self):
            return True

    provider = _ScriptedProvider()
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
    providers_config = {
        assignment.provider: dummy_cfg for assignment in valid_roll_call.assignments
    }

    class _FakeGraph:
        async def ainvoke(self, state, config=None):
            await agent_aggregation_node(state)
            return state

    with (
        patch("orchestration.engine.runner.get_adapter", return_value=provider),
        patch("orchestration.engine.runner.load_providers", return_value=providers_config),
        patch("orchestration.engine.runner.build_graph", return_value=_FakeGraph()),
    ):
        task = asyncio.create_task(start_session(session_id, tmp_data_root, broadcast_fn))
        await all_started.wait()
        state_payload = json.loads((session_dir / "state.json").read_text())
        assert state_payload["substate"] == SessionSubstate.INIT_DISPATCH.value
        release_init.set()
        await task

    init_phase["active"] = False

    journals = [read_journal(session_dir, role_id) for role_id in non_mod_roles]
    assert all(len(j.turns) == 1 for j in journals)
    assert all(j.turns[0].turn_type == TurnType.INIT for j in journals)
    moderator_id = next(r.role_id for r in valid_packet.roles if r.is_moderator)
    mod_journal = read_journal(session_dir, moderator_id)
    assert len(mod_journal.turns) == 1
    assert mod_journal.turns[0].turn_type == TurnType.INIT

    init_events = [
        call[0][1]
        for call in broadcast_fn.call_args_list
        if call[0][1].get("event") in {"agent_response", "moderator_turn"}
    ]
    assert len(init_events) == len(valid_packet.roles)

    bundles = read_all_bundles(session_dir)
    assert len(bundles) == 1
    assert len(bundles[0].responses) == len(non_mod_roles)

    state_payload = json.loads((session_dir / "state.json").read_text())
    assert state_payload["is_cycle_one"] is False
    assert state_payload["substate"] == SessionSubstate.MODERATOR_TURN.value

    state = json.loads((session_dir / "state.json").read_text())
    state["session_dir"] = str(session_dir)
    providers_config = {
        assignment.provider: dummy_cfg for assignment in valid_roll_call.assignments
    }
    with patch("orchestration.engine.nodes.moderator.get_adapter", return_value=provider):
        state = await run_moderator_turn(session_dir, state, broadcast_fn, providers_config)
    save_state(session_dir, strip_runtime(state))

    mod_journal = read_journal(session_dir, moderator_id)
    assert len(mod_journal.turns) == 2
    assert state["pending_action_cards"]
    assert state["substate"] == SessionSubstate.HUMAN_GATE.value

    first_card = state["pending_action_cards"][0]
    state, next_sub = process_gate_event(
        state,
        {
            "type": "dispatch_approved",
            "card_resolutions": [{"card_id": first_card["card_id"], "action": "APPROVED"}],
            "quiz_answers": [],
        },
    )
    assert next_sub == SessionSubstate.AGENT_DISPATCH.value
    save_state(session_dir, strip_runtime(state))

    with patch("orchestration.engine.nodes.dispatch.get_adapter", return_value=provider):
        state = await run_agent_dispatch(session_dir, state, broadcast_fn, providers_config)
    save_state(session_dir, strip_runtime(state))
    assert state["substate"] == SessionSubstate.AGENT_AGGREGATION.value

    approved_role_ids = {first_card["target_role_id"]}
    for role_id in non_mod_roles:
        journal = read_journal(session_dir, role_id)
        expected_turns = 2 if role_id in approved_role_ids else 1
        assert len(journal.turns) == expected_turns

    state[RUNTIME_KEY] = {"broadcast": broadcast_fn, "data_root": tmp_data_root}
    state = await agent_aggregation_node(state)
    save_state(session_dir, strip_runtime(state))

    bundles = read_all_bundles(session_dir)
    assert len(bundles) == 2
    assert state["substate"] == SessionSubstate.MODERATOR_TURN.value
