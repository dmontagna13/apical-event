"""Journal I/O helpers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from core.schemas import AgentJournal, AgentTurn
from core.schemas.constants import JOURNALS_DIR


def _journal_path(session_dir: Path, role_id: str) -> Path:
    return session_dir / JOURNALS_DIR / f"{role_id}_journal.json"


def init_journal(session_dir: Path, role_id: str, session_id: str) -> Path:
    """Initialize an empty journal for an agent."""

    journal = AgentJournal(agent_id=role_id, session_id=session_id, turns=[])
    path = _journal_path(session_dir, role_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, journal.model_dump(mode="json"))
    return path


def append_turn(session_dir: Path, role_id: str, turn: AgentTurn) -> AgentJournal:
    """Append a turn to the agent journal."""

    journal = read_journal(session_dir, role_id)
    prompt_hash = hashlib.sha256(turn.approved_prompt.encode("utf-8")).hexdigest()
    turn_with_hash = turn.model_copy(update={"prompt_hash": prompt_hash})
    journal.turns.append(turn_with_hash)
    _atomic_write(_journal_path(session_dir, role_id), journal.model_dump(mode="json"))
    return journal


def read_journal(session_dir: Path, role_id: str) -> AgentJournal:
    """Read a journal from disk."""

    path = _journal_path(session_dir, role_id)
    data = json.loads(path.read_text())
    return AgentJournal.model_validate(data)


def read_all_journals(session_dir: Path) -> list[AgentJournal]:
    """Read all journals in the session directory."""

    journals_dir = session_dir / JOURNALS_DIR
    journals = []
    for path in sorted(journals_dir.glob("*_journal.json")):
        data = json.loads(path.read_text())
        journals.append(AgentJournal.model_validate(data))
    return journals


def _atomic_write(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)
