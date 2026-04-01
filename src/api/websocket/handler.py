"""WebSocket handler."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import get_data_root
from api.websocket.events import error_event, state_sync_event
from api.websocket.manager import ConnectionManager
from core.journals import load_state, read_all_bundles, read_all_journals
from core.schemas.enums import ErrorCode, SessionSubstate

manager = ConnectionManager()


def _session_dir(data_root: Path, session_id: str) -> Path:
    for project_dir in (data_root / "projects").glob("*"):
        candidate = project_dir / "sessions" / session_id
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Session not found: {session_id}")


def _build_state_sync(session_dir: Path) -> dict:
    state = load_state(session_dir)
    journals = [journal.model_dump(mode="json") for journal in read_all_journals(session_dir)]
    bundles = [bundle.model_dump(mode="json") for bundle in read_all_bundles(session_dir)]
    return {
        "chat_history": state.get("chat_history", []),
        "kanban": state.get("kanban"),
        "pending_actions": state.get("pending_action_cards", []),
        "pending_quizzes": state.get("pending_quizzes", []),
        "session_state": state.get("state"),
        "substate": state.get("substate"),
        "journals": journals,
        "bundles": bundles,
    }


async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Handle websocket connections for a session."""

    data_root = get_data_root()
    await manager.connect(session_id, websocket)
    try:
        session_dir = _session_dir(data_root, session_id)
        await websocket.send_json(state_sync_event(_build_state_sync(session_dir)))
        while True:
            message = await websocket.receive_text()
            payload = json.loads(message)
            event = payload.get("event")
            if event == "dispatch_approved":
                state = load_state(session_dir)
                if state.get("substate") != SessionSubstate.HUMAN_GATE.value:
                    await websocket.send_json(
                        error_event(
                            ErrorCode.CONFLICT,
                            "dispatch_approved not allowed in current substate",
                        )
                    )
            # Other events are handled by the orchestration engine in Phase 4.
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
    except FileNotFoundError:
        await websocket.send_json(error_event(ErrorCode.NOT_FOUND, "Session not found"))
        await websocket.close()
    finally:
        manager.disconnect(session_id, websocket)
