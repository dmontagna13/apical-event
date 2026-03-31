"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.schemas import RollCall, SessionPacket


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
    """Create a temp data root with config/ dir."""

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path
