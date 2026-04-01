"""Seam test: packet to session creation."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_data_root
from core.schemas import SessionPacket


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_data_root] = lambda: tmp_path
    return TestClient(app)


def test_packet_to_session(tmp_path: Path, valid_packet: SessionPacket) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/sessions/init",
        json=valid_packet.model_dump(by_alias=True, mode="json"),
    )
    assert response.status_code == 201
    session_id = response.json()["session_id"]

    session_dir = tmp_path / "projects" / valid_packet.project_name / "sessions" / session_id
    assert (session_dir / "packet.json").exists()
    assert (session_dir / "state.json").exists()
    assert (session_dir / "journals").exists()
    assert (session_dir / "bundles").exists()
    assert (session_dir / "output").exists()
