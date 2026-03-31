"""Roll call preset persistence."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from core.schemas import RoleAssignment, RollCall


class Preset(BaseModel):
    """Named roll call preset."""

    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assignments: list[RoleAssignment]


def _last_roll_call_path(data_root: Path) -> Path:
    return data_root / "config" / "last_roll_call.json"


def _presets_path(data_root: Path) -> Path:
    return data_root / "config" / "roll_call_presets.json"


def load_last_roll_call(data_root: Path) -> RollCall | None:
    """Load the last roll call, if present."""

    path = _last_roll_call_path(data_root)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return RollCall.model_validate(data)


def save_last_roll_call(data_root: Path, roll_call: RollCall) -> None:
    """Persist the last roll call atomically."""

    path = _last_roll_call_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(roll_call.model_dump(mode="json"), indent=2))
    os.replace(tmp_path, path)


def load_presets(data_root: Path) -> list[Preset]:
    """Load named presets, returning an empty list when missing."""

    path = _presets_path(data_root)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "presets" not in data:
        raise ValueError("roll_call_presets.json must contain a 'presets' list")
    return [Preset.model_validate(item) for item in data["presets"]]


def save_preset(data_root: Path, name: str, roll_call: RollCall) -> None:
    """Save or update a named preset."""

    presets = load_presets(data_root)
    now = datetime.utcnow()
    preset = Preset(name=name, created_at=now, assignments=roll_call.assignments)
    updated = False
    for idx, existing in enumerate(presets):
        if existing.name == name:
            presets[idx] = preset
            updated = True
            break
    if not updated:
        presets.append(preset)

    path = _presets_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"presets": [item.model_dump(mode="json") for item in presets]}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)


def delete_preset(data_root: Path, name: str) -> bool:
    """Delete a preset by name, returning False if not found."""

    presets = load_presets(data_root)
    remaining = [preset for preset in presets if preset.name != name]
    if len(remaining) == len(presets):
        return False

    path = _presets_path(data_root)
    payload = {"presets": [item.model_dump(mode="json") for item in remaining]}
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.replace(tmp_path, path)
    return True
