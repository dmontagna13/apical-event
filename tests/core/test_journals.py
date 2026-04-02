"""Journal and bundle I/O tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.journals import (
    append_turn,
    create_session_dir,
    init_journal,
    load_packet,
    load_roll_call,
    load_state,
    next_bundle_id,
    read_all_bundles,
    read_all_journals,
    read_bundle,
    read_bundle_summary,
    read_journal,
    save_roll_call,
    save_state,
    write_bundle,
    write_bundle_summary,
)
from core.schemas import (
    AgentResponseBundle,
    AgentTurn,
    BundledResponse,
    BundleType,
    RoleAssignment,
    RollCall,
    TurnType,
)
from core.schemas.constants import BUNDLES_DIR, JOURNALS_DIR, OUTPUT_DIR


def test_create_session_dir_structure(tmp_path: Path, valid_packet) -> None:
    session_dir = create_session_dir(tmp_path, valid_packet.project_name, "sess_test")
    entries = {path.name for path in session_dir.iterdir()}
    assert entries == {JOURNALS_DIR, BUNDLES_DIR, OUTPUT_DIR}


def test_append_turn_immutable(tmp_session_dir: Path) -> None:
    init_journal(tmp_session_dir, role_id="RG-FAC", session_id="sess_test")
    turn1 = AgentTurn(
        session_id="sess_test",
        role_id="RG-FAC",
        turn_type=TurnType.DELIBERATION,
        bundle_id="bundle_001",
        prompt_hash="",
        approved_prompt="first",
        agent_response="ok",
    )
    append_turn(tmp_session_dir, "RG-FAC", turn1)
    journal_after_first = read_journal(tmp_session_dir, "RG-FAC")
    first_turn_hash = hashlib.sha256(
        json.dumps(journal_after_first.turns[0].model_dump(mode="json"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()

    turn2 = AgentTurn(
        session_id="sess_test",
        role_id="RG-FAC",
        turn_type=TurnType.DELIBERATION,
        bundle_id="bundle_002",
        prompt_hash="",
        approved_prompt="second",
        agent_response="ok",
    )
    append_turn(tmp_session_dir, "RG-FAC", turn2)
    turn3 = AgentTurn(
        session_id="sess_test",
        role_id="RG-FAC",
        turn_type=TurnType.DELIBERATION,
        bundle_id="bundle_003",
        prompt_hash="",
        approved_prompt="third",
        agent_response="ok",
    )
    append_turn(tmp_session_dir, "RG-FAC", turn3)
    journal_after_third = read_journal(tmp_session_dir, "RG-FAC")
    after_turn_hash = hashlib.sha256(
        json.dumps(journal_after_third.turns[0].model_dump(mode="json"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()
    assert first_turn_hash == after_turn_hash
    assert len(journal_after_third.turns) == 3


def test_prompt_hash_computation(tmp_session_dir: Path) -> None:
    init_journal(tmp_session_dir, role_id="RG-FAC", session_id="sess_test")
    turn = AgentTurn(
        session_id="sess_test",
        role_id="RG-FAC",
        turn_type=TurnType.DELIBERATION,
        bundle_id="bundle_001",
        prompt_hash="",
        approved_prompt="hello",
        agent_response="ok",
    )
    journal = append_turn(tmp_session_dir, "RG-FAC", turn)
    expected = hashlib.sha256("hello".encode("utf-8")).hexdigest()
    assert journal.turns[-1].prompt_hash == expected


def test_read_all_journals(tmp_session_dir: Path) -> None:
    init_journal(tmp_session_dir, role_id="RG-FAC", session_id="sess_test")
    init_journal(tmp_session_dir, role_id="RG-CRIT", session_id="sess_test")
    journals = read_all_journals(tmp_session_dir)
    assert {journal.agent_id for journal in journals} == {"RG-FAC", "RG-CRIT"}


def test_bundle_id_generation(tmp_session_dir: Path) -> None:
    assert next_bundle_id(tmp_session_dir) == "bundle_001"
    bundle = AgentResponseBundle(
        bundle_id="bundle_003",
        bundle_type=BundleType.DELIBERATION,
        responses=[
            BundledResponse(
                role_id="RG-FAC",
                turn_id="00000000-0000-0000-0000-000000000000",
                response_text="ok",
                status="OK",
                latency_ms=1,
            )
        ],
    )
    write_bundle(tmp_session_dir, bundle)
    assert next_bundle_id(tmp_session_dir) == "bundle_004"


def test_read_all_bundles_sorted(tmp_session_dir: Path) -> None:
    bundle1 = AgentResponseBundle(
        bundle_id="bundle_002",
        bundle_type=BundleType.DELIBERATION,
        responses=[
            BundledResponse(
                role_id="RG-FAC",
                turn_id="00000000-0000-0000-0000-000000000000",
                response_text="ok",
                status="OK",
                latency_ms=1,
            )
        ],
    )
    bundle2 = AgentResponseBundle(
        bundle_id="bundle_001",
        bundle_type=BundleType.DELIBERATION,
        responses=[
            BundledResponse(
                role_id="RG-CRIT",
                turn_id="00000000-0000-0000-0000-000000000001",
                response_text="ok",
                status="OK",
                latency_ms=1,
            )
        ],
    )
    write_bundle(tmp_session_dir, bundle1)
    write_bundle(tmp_session_dir, bundle2)
    bundles = read_all_bundles(tmp_session_dir)
    assert [bundle.bundle_id for bundle in bundles] == ["bundle_001", "bundle_002"]


def test_bundle_summary_round_trip(tmp_session_dir: Path) -> None:
    write_bundle_summary(tmp_session_dir, "bundle_001", "summary")
    assert read_bundle_summary(tmp_session_dir, "bundle_001") == "summary"


def test_load_functions_missing(tmp_path: Path) -> None:
    session_dir = create_session_dir(tmp_path, "proj", "sess")
    with pytest.raises(FileNotFoundError):
        read_journal(session_dir, "RG-FAC")
    with pytest.raises(FileNotFoundError):
        read_bundle(session_dir, "bundle_001")
    with pytest.raises(FileNotFoundError):
        load_packet(session_dir)
    with pytest.raises(FileNotFoundError):
        load_roll_call(session_dir)
    with pytest.raises(FileNotFoundError):
        load_state(session_dir)


def test_save_and_load_packet_roll_call_state(tmp_session_dir: Path) -> None:
    roll_call = RollCall(
        assignments=[RoleAssignment(role_id="RG-FAC", provider="openai", model="gpt")]
    )
    save_roll_call(tmp_session_dir, roll_call)
    save_state(tmp_session_dir, {"state": "ACTIVE"})
    loaded_roll_call = load_roll_call(tmp_session_dir)
    loaded_state = load_state(tmp_session_dir)
    loaded_packet = load_packet(tmp_session_dir)
    assert loaded_roll_call.assignments[0].role_id == "RG-FAC"
    assert loaded_state["state"] == "ACTIVE"
    assert loaded_packet.packet_id == "BP-2026-02-20-005"
