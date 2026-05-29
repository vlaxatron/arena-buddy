"""Tests for arena_buddy.web.websocket — WebSocket game state broadcasting."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from arena_buddy.web.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_db(tmp_path):
    """Create a FastAPI app with a test database."""
    db_path = tmp_path / "test_ws.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    from arena_buddy.db.schema import create_all
    from arena_buddy.db.seed import seed_all
    create_all(conn)
    seed_all(conn)
    conn.close()
    return create_app(db_path=db_path)


@pytest.fixture
def client(app_with_db):
    """TestClient for the app."""
    return TestClient(app_with_db)


# ---------------------------------------------------------------------------
# WebSocket Manager tests
# ---------------------------------------------------------------------------


class TestWebSocketManager:
    """Tests for the WebSocket connection manager."""

    def test_manager_initial_state(self):
        """New manager has no active connections."""
        from arena_buddy.web.websocket import WebSocketManager
        mgr = WebSocketManager()
        assert len(mgr.active_connections) == 0

    @pytest.mark.asyncio
    async def test_connect_adds_client(self):
        """Connecting a new client increases active count."""
        from arena_buddy.web.websocket import WebSocketManager
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        assert len(mgr.active_connections) == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        """Disconnecting a client decreases active count."""
        from arena_buddy.web.websocket import WebSocketManager
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert len(mgr.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self):
        """Broadcasting a message sends it to all connected clients."""
        from arena_buddy.web.websocket import WebSocketManager
        mgr = WebSocketManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        payload = {"type": "GAME_START", "champion": "Lucian"}
        await mgr.broadcast(payload)

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_skips_disconnected_clients(self):
        """Broadcasting silently handles disconnected clients."""
        from arena_buddy.web.websocket import WebSocketManager
        mgr = WebSocketManager()

        ws = AsyncMock()
        ws.send_json.side_effect = WebSocketDisconnect
        await mgr.connect(ws)

        # Should not raise — disconnected client is removed
        await mgr.broadcast({"type": "STATUS"})
        assert len(mgr.active_connections) == 0

    @pytest.mark.asyncio
    async def test_connect_multiple_same_ws_is_idempotent(self):
        """Connecting the same WebSocket twice is handled correctly."""
        from arena_buddy.web.websocket import WebSocketManager
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        await mgr.connect(ws)
        # Should only be connected once
        assert len(mgr.active_connections) == 1


# ---------------------------------------------------------------------------
# WebSocket Route tests
# ---------------------------------------------------------------------------


class TestWebSocketRoute:
    """Integration tests for the WebSocket endpoint."""

    def test_websocket_endpoint_registered(self, client):
        """The WebSocket route exists in the app."""
        # We can't easily test WebSocket with TestClient (sync),
        # but we can verify the route is registered by checking
        # the app's routes
        app = client.app
        ws_routes = [r for r in app.routes if hasattr(r, "path") and "ws" in str(r.path)]
        assert len(ws_routes) >= 1

    @pytest.mark.asyncio
    async def test_websocket_connect_and_status_event(self, app_with_db):
        """A WebSocket client receives status events on connect."""
        from fastapi.testclient import TestClient as FastAPITestClient

        # Use the TestClient's websocket_connect context manager
        with FastAPITestClient(app_with_db).websocket_connect("/api/ws/game-state") as ws:
            # Should receive an initial status message
            data = ws.receive_json()
            assert data["type"] == "STATUS"
            assert "message" in data
            assert "connected" in data["message"].lower()
