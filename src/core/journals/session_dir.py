"""Session directory lifecycle helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.schemas import RollCall, SessionPacket
from core.schemas.constants import (
    BUNDLES_DIR,
    JOURNALS_DIR,
    OUTPUT_DIR,
    PACKET_FILENAME,
    ROLL_CALL_FILENAME,
    STATE_FILENAME,
)


def get_session_dir(data_root: Path, project_name: str, session_id: str) -> Path:
    """Return the session directory path."""

    return data_root / "projects" / project_name / "sessions" / session_id


def create_session_dir(data_root: Path, project_name: str, session_id: str) -> Path:
    """Create session directory structure."""

    session_dir = get_session_dir(data_root, project_name, session_id)
    (session_dir / JOURNALS_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / BUNDLES_DIR).mkdir(parents=True, exist_ok=True)
    (session_dir / OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    return session_dir


def save_packet(session_dir: Path, packet: SessionPacket) -> Path:
    """Save the session packet JSON."""

    path = session_dir / PACKET_FILENAME
    _atomic_write(path, packet.model_dump(by_alias=True, mode="json"))
    return path


def load_packet(session_dir: Path) -> SessionPacket:
    """Load the session packet JSON."""

    path = session_dir / PACKET_FILENAME
    data = json.loads(path.read_text())
    return SessionPacket.model_validate(data)


def save_roll_call(session_dir: Path, roll_call: RollCall) -> Path:
    """Save the roll call JSON."""

    path = session_dir / ROLL_CALL_FILENAME
    _atomic_write(path, roll_call.model_dump(mode="json"))
    return path


def load_roll_call(session_dir: Path) -> RollCall:
    """Load roll call JSON."""

    path = session_dir / ROLL_CALL_FILENAME
    data = json.loads(path.read_text())
    return RollCall.model_validate(data)


def save_state(session_dir: Path, state: dict) -> Path:
    """Save state JSON."""

    path = session_dir / STATE_FILENAME
    _atomic_write(path, state)
    return path


def load_state(session_dir: Path) -> dict:
    """Load state JSON."""

    path = session_dir / STATE_FILENAME
    return json.loads(path.read_text())


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)
