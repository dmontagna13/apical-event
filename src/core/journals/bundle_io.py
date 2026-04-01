"""Bundle I/O helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.schemas import AgentResponseBundle
from core.schemas.constants import BUNDLE_ID_PAD_WIDTH, BUNDLE_ID_PREFIX, BUNDLES_DIR


def next_bundle_id(session_dir: Path) -> str:
    """Return the next bundle ID."""

    bundles_dir = session_dir / BUNDLES_DIR
    bundles_dir.mkdir(parents=True, exist_ok=True)
    existing = []
    for path in bundles_dir.glob(f"{BUNDLE_ID_PREFIX}*.json"):
        stem = path.stem
        if stem.startswith(BUNDLE_ID_PREFIX):
            suffix = stem[len(BUNDLE_ID_PREFIX) :]
            if suffix.isdigit():
                existing.append(int(suffix))
    next_id = max(existing, default=0) + 1
    return f"{BUNDLE_ID_PREFIX}{next_id:0{BUNDLE_ID_PAD_WIDTH}d}"


def write_bundle(session_dir: Path, bundle: AgentResponseBundle) -> Path:
    """Write bundle JSON to disk."""

    path = session_dir / BUNDLES_DIR / f"{bundle.bundle_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, bundle.model_dump(mode="json"))
    return path


def read_bundle(session_dir: Path, bundle_id: str) -> AgentResponseBundle:
    """Read a bundle by ID."""

    path = session_dir / BUNDLES_DIR / f"{bundle_id}.json"
    data = json.loads(path.read_text())
    return AgentResponseBundle.model_validate(data)


def read_all_bundles(session_dir: Path) -> list[AgentResponseBundle]:
    """Read all bundles sorted by bundle_id."""

    bundles_dir = session_dir / BUNDLES_DIR
    bundles = []
    for path in sorted(bundles_dir.glob(f"{BUNDLE_ID_PREFIX}*.json")):
        data = json.loads(path.read_text())
        bundles.append(AgentResponseBundle.model_validate(data))
    return bundles


def write_bundle_summary(session_dir: Path, bundle_id: str, summary_text: str) -> Path:
    """Write a bundle summary text file."""

    path = session_dir / BUNDLES_DIR / f"{bundle_id}_summary.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(summary_text)
    os.replace(tmp_path, path)
    return path


def read_bundle_summary(session_dir: Path, bundle_id: str) -> str:
    """Read a bundle summary text file."""

    path = session_dir / BUNDLES_DIR / f"{bundle_id}_summary.txt"
    return path.read_text()


def _atomic_write(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)
