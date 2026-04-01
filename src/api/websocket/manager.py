"""WebSocket connection manager."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Track active WebSocket connections per session."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept and register a connection."""

        await websocket.accept()
        self._connections[session_id].add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a connection."""

        self._connections[session_id].discard(websocket)
        if not self._connections[session_id]:
            self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, event: dict) -> None:
        """Broadcast an event to all connections for a session."""

        sockets = list(self._connections.get(session_id, set()))
        if not sockets:
            return
        await asyncio.gather(*(socket.send_json(event) for socket in sockets))
