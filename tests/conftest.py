"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.schemas import RollCall, SessionPacket
from src.core.schemas.constants import PACKET_FILENAME


@pytest.fixture
def valid_packet() -> SessionPacket:
    """Load the valid packet fixture as a SessionPacket."""

    path = Path(__file__).parent / "fixtures" / "valid_packet.json"
    data = json.loads(path.read_text())
    return SessionPacket.model_validate(data)


@pytest.fixture
def valid_roll_call() -> RollCall:
    """Load the valid roll call fixture as a RollCall."""

    path = Path(__file__).parent / "fixtures" / "valid_roll_call.json"
    data = json.loads(path.read_text())
    return RollCall.model_validate(data)


@pytest.fixture
def tmp_data_root(tmp_path: Path) -> Path:
    """Create a temp data root with a default config placeholder."""

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    providers_path = config_dir / "providers.yaml"
    providers_path.write_text("# placeholder providers config\n")
    return tmp_path


@pytest.fixture
def tmp_session_dir(tmp_data_root: Path, valid_packet: SessionPacket) -> Path:
    """Create a session dir with packet saved."""

    session_dir = tmp_data_root / "projects" / valid_packet.project_name / "sessions" / "sess_test"
    session_dir.mkdir(parents=True, exist_ok=True)
    packet_path = session_dir / PACKET_FILENAME
    packet_path.write_text(
        json.dumps(valid_packet.model_dump(by_alias=True, mode="json"), indent=2)
    )
    return session_dir
