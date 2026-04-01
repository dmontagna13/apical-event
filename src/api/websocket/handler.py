"""WebSocket handler."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from api.dependencies import get_data_root
from api.websocket.events import error_event, state_sync_event
from api.websocket.manager import ConnectionManager
from core.journals import load_state, read_all_bundles, read_all_journals, save_state
from core.schemas.enums import ErrorCode, SessionSubstate

logger = logging.getLogger(__name__)
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
    logger.info("WebSocket connect: session=%s data_root=%s", session_id, data_root)
    await manager.connect(session_id, websocket)
    try:
        session_dir = _session_dir(data_root, session_id)
        await websocket.send_json(state_sync_event(_build_state_sync(session_dir)))
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("WebSocket received invalid JSON for session=%s", session_id)
                await websocket.send_json(error_event(ErrorCode.VALIDATION_ERROR, "Invalid JSON payload"))
                continue
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
                else:
                    from orchestration.engine.runner import signal_human_gate

                    data = payload.get("data", {})
                    delivered = await signal_human_gate(
                        session_id,
                        {
                            "type": "dispatch_approved",
                            "card_resolutions": data.get("card_resolutions", []),
                            "quiz_answers": data.get("quiz_answers", []),
                        },
                    )
                    if not delivered:
                        await websocket.send_json(
                            error_event(ErrorCode.CONFLICT, "No engine gate waiting for this session")
                        )
            elif event == "chat_message":
                state = load_state(session_dir)
                substate = state.get("substate")
                if substate == SessionSubstate.HUMAN_GATE.value:
                    from orchestration.engine.runner import signal_human_gate

                    data = payload.get("data", {})
                    await signal_human_gate(
                        session_id,
                        {"type": "chat_message", "content": data.get("content", "")},
                    )
                elif substate in (
                    SessionSubstate.AGENT_DISPATCH.value,
                    SessionSubstate.AGENT_AGGREGATION.value,
                ):
                    # Queue the message — delivered to moderator after dispatch completes
                    state.setdefault("queued_human_messages", []).append(
                        payload.get("data", {}).get("content", "")
                    )
                    save_state(session_dir, state)
                    await websocket.send_json(
                        {"event": "message_queued",
                         "data": {"message": "Message queued — will be delivered after agents respond"}}
                    )
    except WebSocketDisconnect as exc:
        logger.info("WebSocket disconnect: session=%s code=%s", session_id, exc.code)
        manager.disconnect(session_id, websocket)
    except FileNotFoundError:
        logger.warning("WebSocket session not found: session=%s data_root=%s", session_id, data_root)
        await websocket.send_json(error_event(ErrorCode.NOT_FOUND, "Session not found"))
        await websocket.close()
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("WebSocket error: session=%s", session_id)
        await websocket.close()
    finally:
        manager.disconnect(session_id, websocket)
