"""Schema unit tests."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.core.schemas import (
    ActionCard,
    ActionCardStatus,
    AgendaItem,
    AgentJournal,
    AgentResponseBundle,
    AgentTurn,
    BundledResponse,
    DecisionQuiz,
    KanbanBoard,
    KanbanStatus,
    MeetingClass,
    RollCall,
    RoleAssignment,
    SessionState,
    SessionSubstate,
    validate_packet,
)
from src.core.schemas.constants import (
    AGENT_TIMEOUT_SECONDS,
    ARCHIVE_FILENAME,
    BUNDLE_ID_PAD_WIDTH,
    BUNDLE_ID_PREFIX,
    BUNDLES_DIR,
    CONSENSUS_FILENAME,
    CONSENSUS_RETRY_MAX,
    CONTEXT_SAFETY_MARGIN_MIN,
    CONTEXT_SAFETY_MARGIN_RATIO,
    DEFAULT_PORT,
    HEALTH_CHECK_MAX_TOKENS,
    JOURNALS_DIR,
    MODERATOR_RETRY_BACKOFF,
    MODERATOR_RETRY_MAX,
    OUTPUT_DIR,
    PACKET_FILENAME,
    ROLL_CALL_FILENAME,
    SESSION_ID_HEX_LENGTH,
    SESSION_ID_PREFIX,
    STATE_FILENAME,
    SUMMARY_MAX_TOKENS,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
    TOOL_CALL_RETRY_MAX,
)


def test_models_round_trip() -> None:
    roll_call = RollCall(
        assignments=[RoleAssignment(role_id="RG-FAC", provider="openai", model="gpt")]
    )
    roll_call_round = RollCall.model_validate(roll_call.model_dump(mode="json"))
    assert roll_call_round.model_dump(mode="json") == roll_call.model_dump(mode="json")

    turn = AgentTurn(
        session_id="sess_test",
        role_id="RG-FAC",
        bundle_id="bundle_001",
        prompt_hash="abc123",
        approved_prompt="Do the thing",
        agent_response="Done",
    )
    journal = AgentJournal(agent_id="RG-FAC", session_id="sess_test", turns=[turn])
    journal_round = AgentJournal.model_validate(journal.model_dump(mode="json"))
    assert journal_round.model_dump(mode="json") == journal.model_dump(mode="json")

    bundled = BundledResponse(
        role_id="RG-FAC",
        turn_id=turn.turn_id,
        response_text="Response",
        status="OK",
        latency_ms=123,
    )
    bundle = AgentResponseBundle(bundle_id="bundle_001", responses=[bundled])
    bundle_round = AgentResponseBundle.model_validate(bundle.model_dump(mode="json"))
    assert bundle_round.model_dump(mode="json") == bundle.model_dump(mode="json")

    card = ActionCard(target_role_id="RG-CRIT", prompt_text="Prompt", context_note="Context")
    card_round = ActionCard.model_validate(card.model_dump(mode="json"))
    assert card_round.model_dump(mode="json") == card.model_dump(mode="json")

    quiz = DecisionQuiz(decision_title="Pick", options=["A", "B"], context_summary="Context")
    quiz_round = DecisionQuiz.model_validate(quiz.model_dump(mode="json"))
    assert quiz_round.model_dump(mode="json") == quiz.model_dump(mode="json")

    agenda = [AgendaItem(question_id="Q-01", text="Question")]
    board = KanbanBoard.from_agenda(agenda)
    board_round = KanbanBoard.model_validate(board.model_dump(mode="json"))
    assert board_round.model_dump(mode="json") == board.model_dump(mode="json")


def test_uuid_and_datetime_serialize_to_strings() -> None:
    turn = AgentTurn(
        session_id="sess_test",
        role_id="RG-FAC",
        bundle_id="bundle_001",
        prompt_hash="abc123",
        approved_prompt="Do the thing",
        agent_response="Done",
    )
    data = turn.model_dump(mode="json")
    assert isinstance(data["turn_id"], str)
    assert isinstance(data["timestamp"], str)
    assert isinstance(datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")), datetime)
    UUID(data["turn_id"])


def test_validate_packet_valid(valid_packet) -> None:
    assert validate_packet(valid_packet) == []


def test_validate_packet_missing_moderator(valid_packet) -> None:
    roles = [role.model_copy(update={"is_moderator": False}) for role in valid_packet.roles]
    packet = valid_packet.model_copy(update={"roles": roles})
    errors = validate_packet(packet)
    assert any("moderator" in error.lower() for error in errors)


def test_validate_packet_zero_roles(valid_packet) -> None:
    packet = valid_packet.model_copy(update={"roles": []})
    errors = validate_packet(packet)
    assert any("at least 2 roles" in error.lower() for error in errors)


def test_validate_packet_one_role(valid_packet) -> None:
    packet = valid_packet.model_copy(update={"roles": [valid_packet.roles[0]]})
    errors = validate_packet(packet)
    assert any("at least 2 roles" in error.lower() for error in errors)


def test_validate_packet_empty_inputs(valid_packet) -> None:
    packet = valid_packet.model_copy(update={"inputs": []})
    errors = validate_packet(packet)
    assert any("at least 1 input" in error.lower() for error in errors)


def test_validate_packet_duplicate_role_ids(valid_packet) -> None:
    roles = valid_packet.roles[:]
    roles[1] = roles[1].model_copy(update={"role_id": roles[0].role_id})
    packet = valid_packet.model_copy(update={"roles": roles})
    errors = validate_packet(packet)
    assert any("role_id" in error.lower() and "unique" in error.lower() for error in errors)


def test_validate_packet_invalid_role_id_format(valid_packet) -> None:
    roles = valid_packet.roles[:]
    roles[0] = roles[0].model_copy(update={"role_id": "bad"})
    packet = valid_packet.model_copy(update={"roles": roles})
    errors = validate_packet(packet)
    assert any("invalid role_id format" in error.lower() for error in errors)


def test_validate_packet_duplicate_question_ids(valid_packet) -> None:
    agenda = valid_packet.agenda[:]
    agenda[1] = agenda[1].model_copy(update={"question_id": agenda[0].question_id})
    packet = valid_packet.model_copy(update={"agenda": agenda})
    errors = validate_packet(packet)
    assert any("question_id" in error.lower() and "unique" in error.lower() for error in errors)


def test_validate_packet_callback_method(valid_packet) -> None:
    callback = valid_packet.callback.model_copy(update={"method": "http_post"})
    packet = valid_packet.model_copy(update={"callback": callback})
    errors = validate_packet(packet)
    assert any("callback method" in error.lower() for error in errors)


def test_kanban_from_agenda() -> None:
    agenda = [
        AgendaItem(question_id="Q-01", text="Question 1"),
        AgendaItem(question_id="Q-02", text="Question 2"),
    ]
    board = KanbanBoard.from_agenda(agenda)
    assert [task.task_id for task in board.tasks] == ["Q-01", "Q-02"]
    assert all(task.status == KanbanStatus.TO_DISCUSS.value for task in board.tasks)


def test_enum_values() -> None:
    assert {state.value for state in SessionState} == {
        "PACKET_RECEIVED",
        "ROLL_CALL",
        "ACTIVE",
        "CONSENSUS",
        "COMPLETED",
        "ABANDONED",
        "ERROR",
    }
    assert {state.value for state in SessionSubstate} == {
        "MODERATOR_TURN",
        "HUMAN_GATE",
        "AGENT_DISPATCH",
        "AGENT_AGGREGATION",
    }
    assert {state.value for state in MeetingClass} == {
        "DISCOVERY",
        "ADR_DEBATE",
        "DESIGN_SPIKE",
        "RISK_REVIEW",
        "SYNTHESIS",
    }
    assert {status.value for status in KanbanStatus} == {
        "TO_DISCUSS",
        "AGENT_DELIBERATION",
        "PENDING_HUMAN_DECISION",
        "RESOLVED",
    }
    assert {status.value for status in ActionCardStatus} == {
        "PENDING",
        "APPROVED",
        "MODIFIED",
        "DENIED",
    }


def test_constants_values() -> None:
    assert DEFAULT_PORT == 8420
    assert AGENT_TIMEOUT_SECONDS == 120
    assert MODERATOR_RETRY_MAX == 3
    assert MODERATOR_RETRY_BACKOFF == [2, 4, 8]
    assert TOOL_CALL_RETRY_MAX == 3
    assert CONSENSUS_RETRY_MAX == 2
    assert HEALTH_CHECK_MAX_TOKENS == 1
    assert CONTEXT_SAFETY_MARGIN_MIN == 4096
    assert CONTEXT_SAFETY_MARGIN_RATIO == 0.05
    assert SUMMARY_MAX_TOKENS == 256
    assert TOKEN_ESTIMATE_CHARS_PER_TOKEN == 4
    assert SESSION_ID_PREFIX == "sess_"
    assert SESSION_ID_HEX_LENGTH == 8
    assert BUNDLE_ID_PREFIX == "bundle_"
    assert BUNDLE_ID_PAD_WIDTH == 3
    assert PACKET_FILENAME == "packet.json"
    assert ROLL_CALL_FILENAME == "roll_call.json"
    assert STATE_FILENAME == "state.json"
    assert JOURNALS_DIR == "journals"
    assert BUNDLES_DIR == "bundles"
    assert OUTPUT_DIR == "output"
    assert CONSENSUS_FILENAME == "consensus.json"
    assert ARCHIVE_FILENAME == "session_archive.json"
