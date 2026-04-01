"""Session archive construction and atomic output writing (§7.2.6)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.journals import read_all_bundles, read_all_journals
from core.journals.session_dir import load_packet, load_roll_call
from core.schemas.constants import ARCHIVE_FILENAME, CONSENSUS_FILENAME


def build_session_archive(session_dir: Path) -> dict:
    """Assemble a complete session archive as a single JSON-serialisable dict.

    Includes: packet, roll_call, all journals (full turns), all bundles,
    and the consensus output (if already written to output/consensus.json).

    Does NOT include raw API responses, moderator conversation history, or
    any file references — only structured data.
    """
    packet = load_packet(session_dir)
    roll_call = load_roll_call(session_dir)
    journals = read_all_journals(session_dir)
    bundles = read_all_bundles(session_dir)

    # Load consensus output if written
    consensus_path = session_dir / "output" / CONSENSUS_FILENAME
    consensus_data: dict | None = None
    if consensus_path.exists():
        consensus_data = json.loads(consensus_path.read_text())

    return {
        "packet": packet.model_dump(by_alias=True, mode="json"),
        "roll_call": roll_call.model_dump(mode="json"),
        "journals": [j.model_dump(mode="json") for j in journals],
        "bundles": [b.model_dump(mode="json") for b in bundles],
        "consensus": consensus_data,
    }


def write_archive(
    session_dir: Path,
    archive: dict,
    *,
    data_root: Path | None = None,
) -> None:
    """Write all three output files atomically.

    Files written:
    - ``{session_dir}/output/consensus.json``   — consensus output only
    - ``{session_dir}/output/session_archive.json`` — full archive
    - ``{callback.path}``                       — resolved from packet; parent created

    All writes use the atomic write-then-replace pattern.
    """
    output_dir = session_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    consensus_data = archive.get("consensus") or {}

    # 1. consensus.json
    _atomic_write(output_dir / CONSENSUS_FILENAME, consensus_data)

    # 2. session_archive.json
    _atomic_write(output_dir / ARCHIVE_FILENAME, archive)

    # 3. Callback path (from packet)
    packet_data = archive.get("packet", {})
    callback = packet_data.get("callback") or {}
    callback_path_str: str | None = callback.get("path")
    if callback_path_str:
        callback_path = Path(callback_path_str)
        if not callback_path.is_absolute():
            # Resolve relative to data_root; fall back to deriving from session_dir
            base = data_root or _derive_data_root(session_dir)
            callback_path = base / callback_path_str
        callback_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(callback_path, consensus_data)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _derive_data_root(session_dir: Path) -> Path:
    """Compute data_root from session_dir path structure.

    session_dir = data_root/projects/{project}/sessions/{session_id}
    """
    return session_dir.parents[3]


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)
