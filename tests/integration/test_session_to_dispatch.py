"""Integration seam test: init dispatch to first aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from core.journals import append_turn, init_journal, read_all_bundles, save_state
from core.schemas import AgentTurn, KanbanBoard
from core.schemas.enums import SessionSubstate, TurnType
from orchestration.engine.nodes.aggregation import agent_aggregation_node
from orchestration.engine.state import RUNTIME_KEY


@pytest.mark.asyncio
async def test_init_dispatch_to_aggregation(tmp_session_dir, valid_packet):
    session_id = "sess_test"
    packet = valid_packet
    moderator_id = next(r.role_id for r in packet.roles if r.is_moderator)
    background_roles = [r.role_id for r in packet.roles if not r.is_moderator]

    for role_id in background_roles + [moderator_id]:
        init_journal(tmp_session_dir, role_id, session_id)

    for role_id in background_roles:
        turn = AgentTurn(
            turn_id=uuid4(),
            session_id=session_id,
            role_id=role_id,
            turn_type=TurnType.INIT,
            bundle_id=None,
            prompt_hash="",
            approved_prompt="init",
            agent_response=f"init response for {role_id}",
            status="OK",
            error_message=None,
            metadata={"latency_ms": 1},
        )
        append_turn(tmp_session_dir, role_id, turn)

    kanban = KanbanBoard.from_agenda(packet.agenda)
    state = {
        "session_id": session_id,
        "session_dir": str(tmp_session_dir),
        "state": "ACTIVE",
        "substate": SessionSubstate.AGENT_AGGREGATION.value,
        "is_cycle_one": True,
        "kanban": kanban.model_dump(mode="json"),
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "moderator_messages": [],
    }
    save_state(tmp_session_dir, state)

    state[RUNTIME_KEY] = {"broadcast": AsyncMock(), "data_root": tmp_session_dir}
    result_state = await agent_aggregation_node(state)

    bundles = read_all_bundles(tmp_session_dir)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.bundle_id == "bundle_001"
    response_roles = {resp.role_id for resp in bundle.responses}
    assert response_roles == set(background_roles)

    dumped = bundle.model_dump(mode="json")
    assert set(dumped.keys()) >= {"bundle_id", "bundle_type", "timestamp", "responses"}

    assert result_state["is_cycle_one"] is False
    assert result_state["substate"] == SessionSubstate.MODERATOR_TURN.value
