"""API route tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_data_root
from core.schemas import SessionPacket


def _write_providers_yaml(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""
providers:
  openai:
    display_name: "OpenAI"
    base_url: "https://api.openai.com/v1"
    api_key_env: null
    api_key: "key"
    default_model: "gpt-4o"
    available_models:
      - "gpt-4o"
    supports_function_calling: true
    supports_structured_output: true
    max_context_tokens: 128000
  gemini:
    display_name: "Gemini"
    base_url: "https://generativelanguage.googleapis.com/v1beta"
    api_key_env: null
    api_key: "key"
    default_model: "gemini-2.5-pro"
    available_models:
      - "gemini-2.5-pro"
    supports_function_calling: true
    supports_structured_output: true
    max_context_tokens: 1048576
  anthropic:
    display_name: "Anthropic"
    base_url: "https://api.anthropic.com/v1"
    api_key_env: null
    api_key: "key"
    default_model: "claude-3.5-sonnet"
    available_models:
      - "claude-3.5-sonnet"
    supports_function_calling: true
    supports_structured_output: true
    max_context_tokens: 200000
  deepseek:
    display_name: "DeepSeek"
    base_url: "https://api.deepseek.com/v1"
    api_key_env: null
    api_key: "key"
    default_model: "deepseek-chat"
    available_models:
      - "deepseek-chat"
    supports_function_calling: true
    supports_structured_output: false
    max_context_tokens: 65536
""".lstrip())


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_data_root] = lambda: tmp_path
    return TestClient(app)


def test_health() -> None:
    client = _client(Path("/tmp"))
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_init_session_creates_dir(tmp_path: Path, valid_packet: SessionPacket) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/sessions/init",
        json=valid_packet.model_dump(by_alias=True, mode="json"),
    )
    assert response.status_code == 201
    data = response.json()
    session_id = data["session_id"]
    session_dir = tmp_path / "projects" / valid_packet.project_name / "sessions" / session_id
    assert (session_dir / "packet.json").exists()
    assert (session_dir / "state.json").exists()
    assert (session_dir / "journals").exists()
    assert (session_dir / "bundles").exists()
    assert (session_dir / "output").exists()


def test_init_session_idempotent(tmp_path: Path, valid_packet: SessionPacket) -> None:
    client = _client(tmp_path)
    first = client.post(
        "/api/sessions/init",
        json=valid_packet.model_dump(by_alias=True, mode="json"),
    )
    second = client.post(
        "/api/sessions/init",
        json=valid_packet.model_dump(by_alias=True, mode="json"),
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["session_id"] == second.json()["session_id"]


def test_roll_call_transition(tmp_path: Path, valid_packet: SessionPacket, valid_roll_call) -> None:
    _write_providers_yaml(tmp_path / "config" / "providers.yaml")
    client = _client(tmp_path)
    init = client.post(
        "/api/sessions/init",
        json=valid_packet.model_dump(by_alias=True, mode="json"),
    )
    session_id = init.json()["session_id"]
    response = client.post(
        f"/api/sessions/{session_id}/roll-call",
        json=valid_roll_call.model_dump(mode="json"),
    )
    assert response.status_code == 200
    state = client.get(f"/api/sessions/{session_id}/state").json()
    assert state["state"] == "ACTIVE"


def test_roll_call_validation(tmp_path: Path, valid_packet: SessionPacket, valid_roll_call) -> None:
    _write_providers_yaml(tmp_path / "config" / "providers.yaml")
    client = _client(tmp_path)
    init = client.post(
        "/api/sessions/init",
        json=valid_packet.model_dump(by_alias=True, mode="json"),
    )
    session_id = init.json()["session_id"]
    bad_roll_call = valid_roll_call.model_copy(
        update={"assignments": valid_roll_call.assignments[:1]}
    )
    response = client.post(
        f"/api/sessions/{session_id}/roll-call",
        json=bad_roll_call.model_dump(mode="json"),
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
