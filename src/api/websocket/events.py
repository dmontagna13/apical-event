"""WebSocket event helpers."""

from __future__ import annotations

from typing import Any

from core.schemas.enums import ErrorCode


def state_sync_event(data: dict[str, Any]) -> dict:
    """Return a state_sync event payload."""

    return {"event": "state_sync", "data": data}


def error_event(
    code: ErrorCode,
    message: str,
    role_id: str | None = None,
    recoverable: bool = True,
    details: list[str] | None = None,
) -> dict:
    """Return an error event payload."""

    payload = {
        "code": code.value,
        "message": message,
        "recoverable": recoverable,
    }
    if role_id:
        payload["role_id"] = role_id
    if details:
        payload["details"] = details
    return {"event": "error", "data": payload}
