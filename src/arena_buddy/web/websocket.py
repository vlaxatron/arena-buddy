"""WebSocket manager for real-time game state broadcasting.

Manages connected clients and enables the GameOrchestrator to push
game events (start, end, champion detected) to the frontend UI.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts events to all clients.

    Thread-safe — uses a list copy on iteration so broadcast doesn't
    block connections/disconnections.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    @property
    def active_connections(self) -> list[WebSocket]:
        """Return a copy of the active connection list."""
        return list(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and add it to the active set.

        Args:
            websocket: The :class:`WebSocket` to register.
        """
        await websocket.accept()
        if websocket not in self._connections:
            self._connections.append(websocket)
            logger.info("WebSocket client connected (total=%d)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active set.

        Args:
            websocket: The :class:`WebSocket` to remove.
        """
        if websocket in self._connections:
            self._connections.remove(websocket)
            logger.info("WebSocket client disconnected (total=%d)", len(self._connections))

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Send a JSON payload to all connected WebSocket clients.

        Clients that have disconnected are silently removed.

        Args:
            payload: A JSON-serializable dict to send.
        """
        disconnected: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(payload)
            except WebSocketDisconnect:
                disconnected.append(ws)
            except Exception:
                logger.exception("WebSocket broadcast error")
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)
