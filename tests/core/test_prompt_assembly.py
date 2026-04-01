"""Prompt assembly tests."""

from __future__ import annotations

import json
from pathlib import Path

from core.prompt_assembly import (
    assemble_agent_prompt,
    assemble_consensus_prompt,
    assemble_moderator_prompt,
)
from core.schemas import SessionPacket

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_packet() -> SessionPacket:
    data = json.loads((FIXTURES_DIR / "valid_packet.json").read_text())
    return SessionPacket.model_validate(data)


def test_agent_prompt_snapshot() -> None:
    packet = _load_packet()
    role = next(role for role in packet.roles if not role.is_moderator)
    output = assemble_agent_prompt(packet, role)
    expected = (FIXTURES_DIR / "expected_agent_prompt.txt").read_text()
    assert output == expected


def test_moderator_prompt_snapshot() -> None:
    packet = _load_packet()
    role = next(role for role in packet.roles if role.is_moderator)
    non_mod_ids = [r.role_id for r in packet.roles if not r.is_moderator]
    output = assemble_moderator_prompt(
        packet,
        role,
        non_mod_ids,
        tool_definitions_text="TOOL_DEFINITIONS_PLACEHOLDER",
        kanban_state="KANBAN_STATE_PLACEHOLDER",
    )
    expected = (FIXTURES_DIR / "expected_moderator_prompt.txt").read_text()
    assert output == expected


def test_consensus_prompt_snapshot() -> None:
    packet = _load_packet()
    output = assemble_consensus_prompt(packet, session_history="SESSION_HISTORY_PLACEHOLDER")
    expected = (FIXTURES_DIR / "expected_consensus_prompt.txt").read_text()
    assert output == expected


def test_constraints_render_as_bullets() -> None:
    packet = _load_packet()
    role = next(role for role in packet.roles if not role.is_moderator)
    output = assemble_agent_prompt(packet, role)
    for constraint in packet.constraints:
        assert f"- {constraint}" in output


def test_input_headers_rendered() -> None:
    packet = _load_packet()
    role = next(role for role in packet.roles if not role.is_moderator)
    output = assemble_agent_prompt(packet, role)
    for input_doc in packet.inputs:
        if input_doc.status:
            header = f"### {input_doc.path} [{input_doc.status}]"
        else:
            header = f"### {input_doc.path}"
        assert header in output
