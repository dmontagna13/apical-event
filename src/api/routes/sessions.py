"""Session management endpoints."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Response

from api.dependencies import get_data_root, get_providers, get_public_base_url
from core.config import ProviderConfig, resolve_api_key, save_last_roll_call
from core.journals import (
    create_session_dir,
    init_journal,
    read_all_bundles,
    read_all_journals,
    save_packet,
    save_roll_call,
    save_state,
)
from core.providers import get_adapter
from core.schemas import KanbanBoard, RollCall, SessionPacket, validate_packet
from core.schemas.constants import SESSION_ID_HEX_LENGTH, SESSION_ID_PREFIX
from core.schemas.enums import ErrorCode, SessionState, SessionSubstate

router = APIRouter()
logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """API error with structured payload."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        details: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def _error_payload(code: ErrorCode, message: str, details: list[str] | None = None) -> dict:
    return {"error": {"code": code.value, "message": message, "details": details or []}}


def _find_existing_session(data_root: Path, packet_id: str, project_name: str) -> str | None:
    project_dir = data_root / "projects" / project_name / "sessions"
    if not project_dir.exists():
        return None
    for session_dir in project_dir.iterdir():
        if not session_dir.is_dir():
            continue
        packet_path = session_dir / "packet.json"
        if not packet_path.exists():
            continue
        try:
            packet = SessionPacket.model_validate_json(packet_path.read_text())
        except Exception:
            continue
        if packet.packet_id == packet_id:
            return session_dir.name
    return None


def _generate_session_id() -> str:
    return f"{SESSION_ID_PREFIX}{secrets.token_hex(SESSION_ID_HEX_LENGTH // 2)}"


@router.post("/api/sessions/init", status_code=201)
def init_session(
    packet: SessionPacket,
    response: Response,
    data_root: Path = Depends(get_data_root),
) -> dict:
    """Initialize a session from a packet."""

    errors = validate_packet(packet)
    if errors:
        raise ApiError(400, ErrorCode.VALIDATION_ERROR, "Invalid packet", errors)

    existing = _find_existing_session(data_root, packet.packet_id, packet.project_name)
    if existing:
        if response is not None:
            response.status_code = 200
        base_url = get_public_base_url()
        url = f"{base_url}/session/{existing}"
        return {"session_id": existing, "url": url, "state": SessionState.ROLL_CALL.value}

    session_id = _generate_session_id()
    session_dir = create_session_dir(data_root, packet.project_name, session_id)
    save_packet(session_dir, packet)

    for role in packet.roles:
        init_journal(session_dir, role.role_id, session_id)

    kanban = KanbanBoard.from_agenda(packet.agenda)
    state = {
        "session_id": session_id,
        "project_name": packet.project_name,
        "packet_id": packet.packet_id,
        "state": SessionState.ROLL_CALL.value,
        "substate": None,
        "kanban": kanban.model_dump(mode="json"),
        "pending_action_cards": [],
        "pending_quizzes": [],
        "chat_history": [],
        "queued_human_messages": [],
    }
    save_state(session_dir, state)

    base_url = get_public_base_url()
    url = f"{base_url}/session/{session_id}"
    return {"session_id": session_id, "url": url, "state": SessionState.ROLL_CALL.value}


@router.get("/api/sessions/{session_id}")
def get_session(
    session_id: str,
    data_root: Path = Depends(get_data_root),
) -> dict:
    """Return session metadata."""

    session_dir = _find_session_dir(data_root, session_id)
    packet = SessionPacket.model_validate_json((session_dir / "packet.json").read_text())
    state_payload = _read_json(session_dir / "state.json")
    return {
        "session_id": session_id,
        "project_name": packet.project_name,
        "packet_id": packet.packet_id,
        "state": state_payload.get("state"),
        "substate": state_payload.get("substate"),
    }


def _find_session_dir(data_root: Path, session_id: str) -> Path:
    for project_dir in (data_root / "projects").glob("*"):
        session_dir = project_dir / "sessions" / session_id
        if session_dir.exists():
            return session_dir
    raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found")


@router.get("/api/sessions/{session_id}/state")
def get_session_state(session_id: str, data_root: Path = Depends(get_data_root)) -> dict:
    """Return the stored session state."""

    session_dir = _find_session_dir(data_root, session_id)
    state = _read_json(session_dir / "state.json")
    packet = SessionPacket.model_validate_json((session_dir / "packet.json").read_text())
    state["packet"] = packet.model_dump(mode="json", by_alias=True)
    consensus_path = session_dir / "output" / "consensus.json"
    if consensus_path.exists():
        state["consensus"] = _read_json(consensus_path)
    return state


@router.get("/api/sessions/{session_id}/journals")
def get_journals(session_id: str, data_root: Path = Depends(get_data_root)) -> dict:
    """Return all journals for a session."""

    session_dir = _find_session_dir(data_root, session_id)
    journals = read_all_journals(session_dir)
    return {"journals": [journal.model_dump(mode="json") for journal in journals]}


@router.get("/api/sessions/{session_id}/bundles")
def get_bundles(session_id: str, data_root: Path = Depends(get_data_root)) -> dict:
    """Return all bundles for a session."""

    session_dir = _find_session_dir(data_root, session_id)
    bundles = read_all_bundles(session_dir)
    return {"bundles": [bundle.model_dump(mode="json") for bundle in bundles]}


@router.post("/api/sessions/{session_id}/roll-call")
async def submit_roll_call(
    session_id: str,
    roll_call: RollCall,
    background_tasks: BackgroundTasks,
    data_root: Path = Depends(get_data_root),
    providers: dict[str, ProviderConfig] = Depends(get_providers),
) -> dict:
    """Submit roll call assignments."""

    session_dir = _find_session_dir(data_root, session_id)
    packet = SessionPacket.model_validate_json((session_dir / "packet.json").read_text())
    role_ids = {role.role_id for role in packet.roles}
    moderator_id = next(role.role_id for role in packet.roles if role.is_moderator)

    logger.info("Roll call request body: %s", roll_call.model_dump(mode="json"))
    errors = []
    model_cache: dict[str, list[str] | None] = {}
    if {assignment.role_id for assignment in roll_call.assignments} != role_ids:
        errors.append("Roll call assignments must match packet roles.")

    for assignment in roll_call.assignments:
        provider = providers.get(assignment.provider)
        if not provider:
            errors.append(f"Unknown provider: {assignment.provider}")
            continue
        if assignment.model not in provider.available_models:
            if assignment.provider not in model_cache:
                api_key = resolve_api_key(provider)
                if api_key:
                    adapter = get_adapter(
                        assignment.provider, provider.model_copy(update={"api_key": api_key})
                    )
                    try:
                        model_cache[assignment.provider] = await adapter.list_models()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Model discovery failed for %s: %s", assignment.provider, exc
                        )
                        model_cache[assignment.provider] = None
                else:
                    model_cache[assignment.provider] = None
            dynamic_models = model_cache.get(assignment.provider) or []
            if assignment.model not in dynamic_models:
                errors.append(
                    f"Unknown model for provider {assignment.provider}: {assignment.model}"
                )
        if assignment.role_id == moderator_id and not provider.supports_function_calling:
            errors.append("Moderator provider must support function calling.")
        if resolve_api_key(provider) is None:
            errors.append(f"Provider {assignment.provider} has no API key configured.")

    if errors:
        logger.warning("Invalid roll call for session %s: %s", session_id, errors)
        raise ApiError(400, ErrorCode.VALIDATION_ERROR, "Invalid roll call", errors)

    save_roll_call(session_dir, roll_call)
    save_last_roll_call(data_root, roll_call)

    state = _read_json(session_dir / "state.json")
    state["state"] = SessionState.ACTIVE.value
    state["substate"] = SessionSubstate.INIT_DISPATCH.value
    save_state(session_dir, state)

    # Trigger first moderator turn as a background task (TASK-10)
    from api.websocket.handler import manager as ws_manager
    from orchestration.engine.runner import start_session as _start_session

    background_tasks.add_task(
        _start_session,
        session_id,
        data_root,
        ws_manager.broadcast,
    )

    return {"ok": True, "state": SessionState.ACTIVE.value}


@router.post("/api/sessions/{session_id}/abandon")
def abandon_session(session_id: str, data_root: Path = Depends(get_data_root)) -> dict:
    """Mark a session as abandoned."""

    session_dir = _find_session_dir(data_root, session_id)
    state = _read_json(session_dir / "state.json")
    state["state"] = SessionState.ABANDONED.value
    state["substate"] = None
    save_state(session_dir, state)
    return {"ok": True}


@router.get("/api/sessions")
def list_sessions(data_root: Path = Depends(get_data_root)) -> dict:
    """List all sessions."""

    sessions = []
    projects_dir = data_root / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            sessions_dir = project_dir / "sessions"
            if not sessions_dir.exists():
                continue
            for session_dir in sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                packet_path = session_dir / "packet.json"
                state_path = session_dir / "state.json"
                if not packet_path.exists() or not state_path.exists():
                    continue
                packet = SessionPacket.model_validate_json(packet_path.read_text())
                state = _read_json(state_path)
                sessions.append(
                    {
                        "session_id": session_dir.name,
                        "project_name": packet.project_name,
                        "packet_id": packet.packet_id,
                        "state": state.get("state"),
                        "substate": state.get("substate"),
                    }
                )
    return {"sessions": sessions}


def _read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text())
