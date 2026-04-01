"""Seam test: full one-cycle deliberation loop.

init → roll-call → moderator (action cards) → HUMAN_GATE
  → dispatch approved → agent dispatch → aggregation
  → second moderator turn → HUMAN_GATE
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from api.app import create_app
from api.dependencies import get_data_root, get_providers
from core.config import ProviderConfig
from core.journals import load_state, read_all_bundles, read_journal
from core.providers.base import CompletionResult, ToolCall
from core.schemas import RollCall, SessionPacket
from core.schemas.enums import SessionSubstate
from orchestration.engine.runner import signal_human_gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _providers(valid_roll_call: RollCall) -> dict[str, ProviderConfig]:
    providers: dict[str, ProviderConfig] = {}
    for assignment in valid_roll_call.assignments:
        providers[assignment.provider] = ProviderConfig(
            display_name=assignment.provider,
            base_url="http://mock",
            api_key_env=None,
            api_key="test-key",
            default_model=assignment.model,
            available_models=[assignment.model],
            supports_function_calling=True,
            supports_structured_output=False,
            max_context_tokens=32000,
        )
    return providers


def _moderator_adapter():
    """First complete() call returns a generate_action_cards tool call; subsequent calls return plain text."""
    call_count = 0

    class _Mock:
        async def complete(self, messages, model, tools=None, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CompletionResult(
                    text="Dispatching a card to the Critic.",
                    tool_calls=[
                        ToolCall(
                            name="generate_action_cards",
                            arguments={
                                "cards": [
                                    {
                                        "target_role_id": "RG-CRIT",
                                        "prompt_text": "Analyse the proposed domain boundaries.",
                                        "context_note": "Need adversarial review.",
                                    }
                                ]
                            },
                        )
                    ],
                    usage={},
                    finish_reason="tool_use",
                    latency_ms=1,
                )
            return CompletionResult(
                text="Synthesis complete. Awaiting further deliberation.",
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

    return _Mock()


def _agent_adapter(text: str = "Boundary analysis: the domains are well-separated."):
    class _Mock:
        async def complete(self, messages, model, tools=None, **kw):
            return CompletionResult(
                text=text,
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

    return _Mock()


async def _wait_for_substate(session_dir: Path, target: str, timeout: float = 5.0) -> dict:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        state = load_state(session_dir)
        if state.get("substate") == target:
            return state
        await asyncio.sleep(0.02)
    raise TimeoutError(f"Did not reach substate '{target}' within {timeout}s")


async def _wait_for_bundle(session_dir: Path, timeout: float = 5.0) -> None:
    """Wait until at least one AgentResponseBundle has been written to disk."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if read_all_bundles(session_dir):
            return
        await asyncio.sleep(0.02)
    raise TimeoutError("No bundle written within {timeout}s")


def _find_session_dir(tmp_path: Path, project_name: str, session_id: str) -> Path:
    return tmp_path / "projects" / project_name / "sessions" / session_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_deliberation_loop(
    tmp_path: Path,
    valid_packet: SessionPacket,
    valid_roll_call: RollCall,
) -> None:
    """Full one-cycle deliberation loop with mocked providers.

    Verifies:
    1. Engine runs first moderator turn and produces action cards.
    2. HUMAN_GATE is reached; pending_action_cards are populated.
    3. Human approves cards via signal_human_gate.
    4. Engine runs AGENT_DISPATCH — journals are written, bundles created.
    5. Engine runs second moderator turn.
    6. Engine reaches HUMAN_GATE again; chat_history has two moderator entries.
    """
    providers = _providers(valid_roll_call)
    moderator = _moderator_adapter()
    agent = _agent_adapter()

    app = create_app()
    app.dependency_overrides[get_data_root] = lambda: tmp_path
    app.dependency_overrides[get_providers] = lambda: providers

    with (
        patch("orchestration.engine.runner._load_providers", return_value=providers),
        patch("orchestration.engine.nodes.moderator.get_adapter", return_value=moderator),
        patch("orchestration.engine.nodes.dispatch.get_adapter", return_value=agent),
    ):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1. Init session
            resp = await client.post(
                "/api/sessions/init",
                json=valid_packet.model_dump(by_alias=True, mode="json"),
            )
            assert resp.status_code == 201
            session_id = resp.json()["session_id"]
            session_dir = _find_session_dir(tmp_path, valid_packet.project_name, session_id)

            # 2. Submit roll call — engine starts as background asyncio task
            resp = await client.post(
                f"/api/sessions/{session_id}/roll-call",
                json=valid_roll_call.model_dump(by_alias=True, mode="json"),
            )
            assert resp.status_code == 200

        # 3. Yield to event loop; engine runs first moderator turn
        await asyncio.sleep(0)

        # 4. Wait for first HUMAN_GATE
        state = await _wait_for_substate(session_dir, SessionSubstate.HUMAN_GATE.value)
        assert state["pending_action_cards"], "Moderator should have generated action cards"
        assert any(
            e["role"] == "moderator" for e in state.get("chat_history", [])
        ), "First moderator turn should be in chat_history"

        # 5. Approve all pending cards
        pending = state["pending_action_cards"]
        card_resolutions = [
            {"card_id": str(c["card_id"]), "action": "APPROVED"} for c in pending
        ]
        delivered = await signal_human_gate(
            session_id,
            {
                "type": "dispatch_approved",
                "card_resolutions": card_resolutions,
                "quiz_answers": [],
            },
        )
        assert delivered, "Human gate queue should be registered"

        # 6. Wait for agent dispatch + aggregation (bundle written)
        await asyncio.sleep(0)
        await _wait_for_bundle(session_dir)

        # 7. Wait for second HUMAN_GATE (after second moderator turn)
        state = await _wait_for_substate(session_dir, SessionSubstate.HUMAN_GATE.value)

    # --- Assertions ---

    # Engine is at second HUMAN_GATE
    assert state["substate"] == SessionSubstate.HUMAN_GATE.value
    assert state["state"] == "ACTIVE"

    # At least one bundle was written
    bundles = read_all_bundles(session_dir)
    assert len(bundles) >= 1

    # Agent journal for RG-CRIT has the dispatched turn
    agent_journal = read_journal(session_dir, "RG-CRIT")
    assert len(agent_journal.turns) >= 1
    assert agent_journal.turns[0].approved_prompt == "Analyse the proposed domain boundaries."
    assert agent_journal.turns[0].status == "OK"
    assert agent_journal.turns[0].agent_response == "Boundary analysis: the domains are well-separated."

    # chat_history has two moderator entries (first turn + second turn)
    moderator_msgs = [e for e in state.get("chat_history", []) if e["role"] == "moderator"]
    assert len(moderator_msgs) >= 2, "Both moderator turns should be in chat_history"
