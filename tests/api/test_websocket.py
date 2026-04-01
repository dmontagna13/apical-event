"""WebSocket tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_data_root
from core.journals import create_session_dir, save_packet, save_state


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_data_root] = lambda: tmp_path
    return TestClient(app)


def test_state_sync_on_connect(tmp_path: Path, valid_packet, monkeypatch) -> None:
    monkeypatch.setenv("APICAL_DATA", str(tmp_path))
    session_dir = create_session_dir(tmp_path, valid_packet.project_name, "sess_test")
    save_packet(session_dir, valid_packet)
    save_state(
        session_dir,
        {
            "state": "ACTIVE",
            "substate": "HUMAN_GATE",
            "kanban": {"tasks": []},
            "pending_action_cards": [],
            "pending_quizzes": [],
            "chat_history": [],
            "queued_human_messages": [],
        },
    )

    client = _client(tmp_path)
    with client.websocket_connect("/ws/session/sess_test") as websocket:
        event = websocket.receive_json()
        assert event["event"] == "state_sync"
        assert event["data"]["session_state"] == "ACTIVE"


def test_dispatch_invalid_substate(tmp_path: Path, valid_packet, monkeypatch) -> None:
    monkeypatch.setenv("APICAL_DATA", str(tmp_path))
    session_dir = create_session_dir(tmp_path, valid_packet.project_name, "sess_test")
    save_packet(session_dir, valid_packet)
    save_state(
        session_dir,
        {
            "state": "ACTIVE",
            "substate": "MODERATOR_TURN",
            "kanban": {"tasks": []},
            "pending_action_cards": [],
            "pending_quizzes": [],
            "chat_history": [],
            "queued_human_messages": [],
        },
    )

    client = _client(tmp_path)
    with client.websocket_connect("/ws/session/sess_test") as websocket:
        websocket.receive_json()
        websocket.send_json({"event": "dispatch_approved", "data": {}})
        response = websocket.receive_json()
        assert response["event"] == "error"
        assert response["data"]["code"] == "CONFLICT"
