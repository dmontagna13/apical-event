"""Unit tests for orchestration/consensus (TASK-12)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.journals import init_journal, save_state
from core.journals.session_dir import save_packet, save_roll_call
from core.providers.base import CompletionResult
from core.schemas import RollCall, SessionPacket
from core.schemas.constants import ARCHIVE_FILENAME, CONSENSUS_FILENAME
from core.schemas.enums import SessionState
from orchestration.consensus.archive import build_session_archive, write_archive
from orchestration.consensus.capture import run_consensus_capture
from orchestration.consensus.validator import validate_consensus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PACKET_PATH = Path(__file__).parent.parent / "fixtures" / "valid_packet.json"
_ROLL_CALL_PATH = Path(__file__).parent.parent / "fixtures" / "valid_roll_call.json"


def _load_packet() -> SessionPacket:
    return SessionPacket.model_validate(json.loads(_PACKET_PATH.read_text()))


def _load_roll_call() -> RollCall:
    return RollCall.model_validate(json.loads(_ROLL_CALL_PATH.read_text()))


def _valid_output(packet: SessionPacket) -> dict:
    """Build a minimal consensus output dict that passes validation."""
    return_header = {field: "PRESENT" for field in packet.output_contract.return_header_fields}
    return {
        "packet_id": packet.packet_id,
        "session_id": "sess_test",
        "completed_at": "2026-01-01T00:00:00Z",
        "return_header": return_header,
        "sections": {
            "PRIMARY_DOMAINS_COUNT": {"value": 5},
            "DOMAIN_DECISIONS_MAPPING": {"domains": [{"domain_name": "Auth"}]},
            "INTERFACE_CANDIDATES": {
                "interfaces": [
                    {"interface_id": "IF-01"},
                    {"interface_id": "IF-02"},
                    {"interface_id": "IF-03"},
                ]
            },
            "DECISION_ROADMAP": {
                "gates": [
                    {"gate_number": 1},
                    {"gate_number": 2},
                ]
            },
        },
        "stop_condition_met": True,
        "dissenting_opinions": [],
        "session_statistics": {
            "total_turns": 4,
            "agent_turns": {"RG-CRIT": 1},
            "human_decisions": 1,
            "duration_minutes": 10,
        },
    }


def _make_session_dir(tmp_path: Path) -> Path:
    from core.journals import create_session_dir

    packet = _load_packet()
    roll_call = _load_roll_call()
    session_dir = create_session_dir(tmp_path, packet.project_name, "sess_test")
    save_packet(session_dir, packet)
    save_roll_call(session_dir, roll_call)
    for role in packet.roles:
        init_journal(session_dir, role.role_id, "sess_test")
    state = {
        "session_id": "sess_test",
        "state": SessionState.CONSENSUS.value,
        "substate": None,
        "kanban": {},
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
        "moderator_messages": [],
    }
    save_state(session_dir, state)
    return session_dir


def _mock_provider(text: str):
    class _Mock:
        async def complete(self, messages, model, tools=None, response_format=None, **kw):
            return CompletionResult(
                text=text,
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

    return _Mock()


def _providers_config() -> dict:
    from core.config import ProviderConfig

    cfg = ProviderConfig(
        display_name="mock",
        base_url="http://mock",
        api_key_env=None,
        api_key="test-key",
        default_model="mock-model",
        available_models=["gpt-4o", "gemini-2.5-pro", "claude-3.5-sonnet", "deepseek-chat"],
        supports_function_calling=True,
        supports_structured_output=True,
        max_context_tokens=32000,
    )
    return {"openai": cfg, "gemini": cfg, "anthropic": cfg, "deepseek": cfg}


# ---------------------------------------------------------------------------
# validator tests
# ---------------------------------------------------------------------------


def test_validate_valid_output():
    """Empty errors list for a fully valid output."""
    packet = _load_packet()
    output = _valid_output(packet)
    errors = validate_consensus(output, packet.output_contract)
    assert errors == []


def test_validate_missing_return_header_field():
    packet = _load_packet()
    output = _valid_output(packet)
    # Remove one header field
    del output["return_header"][packet.output_contract.return_header_fields[0]]
    errors = validate_consensus(output, packet.output_contract)
    assert any("return_header" in e for e in errors)
    assert any(packet.output_contract.return_header_fields[0] in e for e in errors)


def test_validate_missing_required_section():
    packet = _load_packet()
    output = _valid_output(packet)
    missing_section = packet.output_contract.required_sections[0]
    del output["sections"][missing_section]
    errors = validate_consensus(output, packet.output_contract)
    assert any(missing_section in e for e in errors)


def test_validate_section_below_minimum_count():
    """INTERFACE_CANDIDATES with fewer than 3 interfaces should produce an error."""
    packet = _load_packet()
    output = _valid_output(packet)
    # Only 1 interface (minimum is 3)
    output["sections"]["INTERFACE_CANDIDATES"] = {"interfaces": [{"interface_id": "IF-01"}]}
    errors = validate_consensus(output, packet.output_contract)
    assert any("INTERFACE_CANDIDATES" in e for e in errors)


def test_validate_roadmap_below_minimum_count():
    """DECISION_ROADMAP with fewer than 2 gates (minimum_counts key: DECISION_ROADMAP_GATES)."""
    packet = _load_packet()
    output = _valid_output(packet)
    output["sections"]["DECISION_ROADMAP"] = {"gates": [{"gate_number": 1}]}  # only 1
    errors = validate_consensus(output, packet.output_contract)
    assert any("DECISION_ROADMAP" in e for e in errors)


def test_validate_stop_condition_false_is_warning():
    """stop_condition_met=False produces a 'Warning:' entry, not a hard error."""
    packet = _load_packet()
    output = _valid_output(packet)
    output["stop_condition_met"] = False
    errors = validate_consensus(output, packet.output_contract)
    # Should have exactly one entry — the warning
    assert len(errors) == 1
    assert errors[0].startswith("Warning:")


def test_validate_stop_condition_true_no_warning():
    packet = _load_packet()
    output = _valid_output(packet)
    output["stop_condition_met"] = True
    errors = validate_consensus(output, packet.output_contract)
    assert not any(e.startswith("Warning:") for e in errors)


# ---------------------------------------------------------------------------
# archive tests
# ---------------------------------------------------------------------------


def test_build_session_archive(tmp_path: Path):
    session_dir = _make_session_dir(tmp_path)
    archive = build_session_archive(session_dir)
    assert "packet" in archive
    assert "roll_call" in archive
    assert "journals" in archive
    assert "bundles" in archive
    assert isinstance(archive["journals"], list)
    assert isinstance(archive["bundles"], list)
    assert archive["packet"]["packet_id"] == _load_packet().packet_id


def test_build_session_archive_includes_consensus(tmp_path: Path):
    session_dir = _make_session_dir(tmp_path)
    consensus_data = {"packet_id": "test", "stop_condition_met": True}
    output_dir = session_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / CONSENSUS_FILENAME).write_text(json.dumps(consensus_data))

    archive = build_session_archive(session_dir)
    assert archive["consensus"] == consensus_data


def test_write_archive_creates_output_files(tmp_path: Path):
    session_dir = _make_session_dir(tmp_path)
    packet = _load_packet()
    consensus_data = _valid_output(packet)
    (session_dir / "output").mkdir(parents=True, exist_ok=True)
    (session_dir / "output" / CONSENSUS_FILENAME).write_text(json.dumps(consensus_data))

    archive = build_session_archive(session_dir)
    write_archive(session_dir, archive, data_root=tmp_path)

    assert (session_dir / "output" / CONSENSUS_FILENAME).exists()
    assert (session_dir / "output" / ARCHIVE_FILENAME).exists()


def test_write_archive_creates_callback_parent(tmp_path: Path):
    """Callback path's parent directory is created if it doesn't exist."""
    session_dir = _make_session_dir(tmp_path)
    packet = _load_packet()
    consensus_data = _valid_output(packet)
    (session_dir / "output").mkdir(parents=True, exist_ok=True)
    (session_dir / "output" / CONSENSUS_FILENAME).write_text(json.dumps(consensus_data))

    archive = build_session_archive(session_dir)
    write_archive(session_dir, archive, data_root=tmp_path)

    # callback.path = "04_BREAKOUTS/RETURNS/..." (from valid_packet.json)
    callback_path_str = packet.callback.path
    callback_path = tmp_path / callback_path_str
    assert callback_path.exists(), f"Callback file should exist at {callback_path}"


def test_write_archive_is_single_json_dict(tmp_path: Path):
    """Session archive must be a single flat JSON dict (no nested paths)."""
    session_dir = _make_session_dir(tmp_path)
    consensus_data = _valid_output(_load_packet())
    (session_dir / "output").mkdir(parents=True, exist_ok=True)
    (session_dir / "output" / CONSENSUS_FILENAME).write_text(json.dumps(consensus_data))

    archive = build_session_archive(session_dir)
    write_archive(session_dir, archive, data_root=tmp_path)

    archive_path = session_dir / "output" / ARCHIVE_FILENAME
    loaded = json.loads(archive_path.read_text())
    assert isinstance(loaded, dict)
    # Must have the expected top-level keys
    for key in ("packet", "roll_call", "journals", "bundles"):
        assert key in loaded, f"Archive missing key: {key}"


# ---------------------------------------------------------------------------
# capture tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_consensus_capture_success(tmp_path: Path):
    """Valid JSON response → consensus.json and archive written, state = COMPLETED."""
    session_dir = _make_session_dir(tmp_path)
    packet = _load_packet()
    output = _valid_output(packet)

    state = {
        "session_id": "sess_test",
        "state": SessionState.CONSENSUS.value,
        "substate": None,
    }

    manager = MagicMock()
    manager.broadcast = AsyncMock()

    providers_cfg = _providers_config()

    with patch("orchestration.consensus.capture.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider(json.dumps(output))
        result_state = await run_consensus_capture(
            session_dir, state, manager, providers_cfg, data_root=tmp_path
        )

    assert result_state["state"] == SessionState.COMPLETED.value
    assert (session_dir / "output" / CONSENSUS_FILENAME).exists()
    assert (session_dir / "output" / ARCHIVE_FILENAME).exists()
    manager.broadcast.assert_called()


@pytest.mark.asyncio
async def test_run_consensus_capture_retries_on_validation_failure(tmp_path: Path):
    """On hard validation error, re-prompts up to CONSENSUS_RETRY_MAX times."""
    session_dir = _make_session_dir(tmp_path)
    packet = _load_packet()

    # First response: missing required sections
    bad_output = {
        "packet_id": packet.packet_id,
        "session_id": "sess_test",
        "completed_at": "2026-01-01T00:00:00Z",
        "return_header": {f: "X" for f in packet.output_contract.return_header_fields},
        "sections": {},  # Missing all required sections
        "stop_condition_met": True,
        "dissenting_opinions": [],
        "session_statistics": {
            "total_turns": 0,
            "agent_turns": {},
            "human_decisions": 0,
            "duration_minutes": 0,
        },
    }
    good_output = _valid_output(packet)

    call_count = 0

    class _CountingProvider:
        async def complete(self, messages, model, tools=None, response_format=None, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CompletionResult(
                    text=json.dumps(bad_output),
                    tool_calls=[],
                    usage={},
                    finish_reason="stop",
                    latency_ms=1,
                )
            return CompletionResult(
                text=json.dumps(good_output),
                tool_calls=[],
                usage={},
                finish_reason="stop",
                latency_ms=1,
            )

    state = {"session_id": "sess_test", "state": SessionState.CONSENSUS.value, "substate": None}
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    with patch("orchestration.consensus.capture.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _CountingProvider()
        result_state = await run_consensus_capture(
            session_dir, state, manager, _providers_config(), data_root=tmp_path
        )

    assert call_count >= 2, "Should retry at least once"
    assert result_state["state"] == SessionState.COMPLETED.value


@pytest.mark.asyncio
async def test_run_consensus_capture_writes_warnings_after_max_retries(tmp_path: Path):
    """After CONSENSUS_RETRY_MAX retries still failing, output includes validation_warnings."""

    session_dir = _make_session_dir(tmp_path)
    packet = _load_packet()

    # Output that always fails (empty sections)
    bad_output = {
        "packet_id": packet.packet_id,
        "session_id": "sess_test",
        "completed_at": "2026-01-01T00:00:00Z",
        "return_header": {f: "X" for f in packet.output_contract.return_header_fields},
        "sections": {},
        "stop_condition_met": True,
        "dissenting_opinions": [],
        "session_statistics": {
            "total_turns": 0,
            "agent_turns": {},
            "human_decisions": 0,
            "duration_minutes": 0,
        },
    }

    state = {"session_id": "sess_test", "state": SessionState.CONSENSUS.value, "substate": None}
    manager = MagicMock()
    manager.broadcast = AsyncMock()

    with patch("orchestration.consensus.capture.get_adapter") as mock_get_adapter:
        mock_get_adapter.return_value = _mock_provider(json.dumps(bad_output))
        result_state = await run_consensus_capture(
            session_dir, state, manager, _providers_config(), data_root=tmp_path
        )

    assert result_state["state"] == SessionState.COMPLETED.value

    # consensus.json should exist with validation_warnings
    consensus_path = session_dir / "output" / CONSENSUS_FILENAME
    assert consensus_path.exists()
    written = json.loads(consensus_path.read_text())
    assert "validation_warnings" in written
    assert len(written["validation_warnings"]) > 0
