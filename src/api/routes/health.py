"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    """Return basic health status."""

    return {"ok": True}
