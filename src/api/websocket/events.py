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


def init_dispatch_started(role_ids: list[str]) -> dict:
    """Return init_dispatch_started event payload."""

    return {"event": "init_dispatch_started", "data": {"role_ids": role_ids}}


def init_dispatch_complete(success_count: int, error_count: int) -> dict:
    """Return init_dispatch_complete event payload."""

    return {
        "event": "init_dispatch_complete",
        "data": {"success_count": success_count, "error_count": error_count},
    }


def error_state_entered(message: str, failed_role: str, retry_count: int) -> dict:
    """Return error_state_entered event payload."""

    return {
        "event": "error_state_entered",
        "data": {"message": message, "failed_role": failed_role, "retry_count": retry_count},
    }
