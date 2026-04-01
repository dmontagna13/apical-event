"""Seam test: submit_roll_call → engine starts → first moderator turn → HUMAN_GATE."""

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
from core.journals import load_state
from core.providers.base import CompletionResult
from core.schemas import RollCall, SessionPacket
from core.schemas.enums import SessionSubstate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _providers(valid_roll_call: RollCall) -> dict[str, ProviderConfig]:
    """Return a ProviderConfig for every provider in the roll call."""
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


def _mock_adapter(text: str = "Deliberation begun."):
    """Return a mock ProviderAdapter that always returns plain text."""

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
    raise TimeoutError(f"Session did not reach substate '{target}' within {timeout}s")


def _find_session_dir(tmp_path: Path, project_name: str, session_id: str) -> Path:
    return tmp_path / "projects" / project_name / "sessions" / session_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_to_dispatch(
    tmp_path: Path,
    valid_packet: SessionPacket,
    valid_roll_call: RollCall,
) -> None:
    """After submitting a roll call, the engine runs one moderator turn and waits at HUMAN_GATE.

    This seam test verifies that:
    1. POST /api/sessions/init creates the session on disk.
    2. POST /api/sessions/{id}/roll-call transitions state to ACTIVE and starts the engine.
    3. The engine executes the first MODERATOR_TURN node.
    4. The moderator response is recorded in chat_history.
    5. Substate reaches HUMAN_GATE (engine is waiting for human input).
    """
    providers = _providers(valid_roll_call)
    adapter = _mock_adapter("Let us begin deliberating on the agenda.")

    app = create_app()
    app.dependency_overrides[get_data_root] = lambda: tmp_path
    app.dependency_overrides[get_providers] = lambda: providers

    with (
        patch("orchestration.engine.runner._load_providers", return_value=providers),
        patch("orchestration.engine.nodes.moderator.get_adapter", return_value=adapter),
    ):
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # 1. Create session
            resp = await client.post(
                "/api/sessions/init",
                json=valid_packet.model_dump(by_alias=True, mode="json"),
            )
            assert resp.status_code == 201
            session_id = resp.json()["session_id"]
            session_dir = _find_session_dir(tmp_path, valid_packet.project_name, session_id)

            # 2. Submit roll call — background task fires start_session
            resp = await client.post(
                f"/api/sessions/{session_id}/roll-call",
                json=valid_roll_call.model_dump(by_alias=True, mode="json"),
            )
            assert resp.status_code == 200
            assert resp.json()["state"] == "ACTIVE"

        # 3. Yield to event loop so the engine task can start running
        await asyncio.sleep(0)

        # 4. Wait for HUMAN_GATE (patches remain active during engine execution)
        state = await _wait_for_substate(session_dir, SessionSubstate.HUMAN_GATE.value)

    assert state["substate"] == SessionSubstate.HUMAN_GATE.value
    assert state["state"] == "ACTIVE"
    assert any(
        entry["role"] == "moderator" for entry in state.get("chat_history", [])
    ), "Moderator turn should be recorded in chat_history"
