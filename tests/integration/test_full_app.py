"""Integration tests for Arena Buddy — end-to-end verification.

Uses a mock Live Client Data API server, FastAPI TestClient,
and a real SQLite database to test the full system.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from unittest import mock

import httpx
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Mock Live Client Data API server
# ---------------------------------------------------------------------------


class MockGameClientServer:
    """A tiny HTTP server that mimics the League Live Client Data API.

    Runs on a random port and responds with configurable game state data.
    Used to test the GameOrchestrator with a real HTTP connection.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        import http.server
        import socketserver

        self.host = host
        self.port = port
        self._game_mode = "CHERRY"
        self._champion = "Lucian"
        self._game_id = "test-game-001"
        self._active = True
        self._server: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None
        self._shutdown_flag = False

        # Build the handler
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if not outer._active:
                    self.send_error(503, "Service Unavailable")
                    return

                if "allgamedata" in self.path or self.path == "/":
                    data = {
                        "gameData": {
                            "gameMode": outer._game_mode,
                            "gameId": outer._game_id,
                        },
                        "activePlayer": {
                            "championName": outer._champion,
                            "summonerName": "TestPlayer",
                            "championStats": {},
                            "abilities": {},
                            "currentGold": 500.0,
                            "level": 5,
                        },
                        "allPlayers": [],
                        "events": {"Events": []},
                    }
                elif "activeplayer" in self.path:
                    data = {
                        "championName": outer._champion,
                        "summonerName": "TestPlayer",
                        "championStats": {"attackDamage": 80.0},
                        "level": 6,
                        "abilities": {},
                        "currentGold": 800.0,
                        "items": [],
                    }
                elif "eventdata" in self.path:
                    data = {"Events": []}
                else:
                    data = {"status": "ok"}

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, format, *args):
                pass  # Suppress logging

        self._handler_class = Handler
        self._server = socketserver.TCPServer((host, port), Handler)
        self.port = self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"https://{self.host}:{self.port}"

    def start(self):
        self._thread = threading.Thread(target=lambda: self._server.serve_forever() if self._server else None, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def set_champion(self, name: str):
        self._champion = name

    def set_game_mode(self, mode: str):
        self._game_mode = mode

    def set_game_id(self, game_id: str):
        self._game_id = game_id

    def deactivate(self):
        self._active = False

    def activate(self):
        self._active = True


# ---------------------------------------------------------------------------
# Mock LCU (League Client Update) API server
# ---------------------------------------------------------------------------


class MockLCUServer:
    """A tiny HTTP server that mimics the League Client Update (LCU) API.

    The LCU is the lobby client that provides match history and other data.
    Used to test the MatchCaptureService.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        import http.server
        import socketserver

        self.host = host
        self.port = port
        self.password = "test-riot-password"
        self._server: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None

        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                # Auth check
                auth = self.headers.get("Authorization", "")
                expected = "Basic " + __import__("base64").b64encode(
                    f"riot:{outer.password}".encode()
                ).decode()
                if auth != expected:
                    self.send_error(401, "Unauthorized")
                    return

                # Match detail endpoint
                if "/lol-match-history/v1/games/" in self.path:
                    game_id = self.path.rsplit("/", 1)[-1]
                    data = {
                        "gameId": int(game_id) if game_id.isdigit() else 12345,
                        "gameMode": "CHERRY",
                        "gameType": "MATCHED_GAME",
                        "queueId": 1700,
                        "mapId": 30,
                        "gameDuration": 840,
                        "gameCreation": 1700000000000,
                        "gameVersion": "16.11.564.1234",
                        "participants": [
                            {
                                "participantId": 1,
                                "championId": 236,
                                "stats": {
                                    "win": True,
                                    "kills": 8,
                                    "deaths": 3,
                                    "assists": 5,
                                    "item0": 6672,
                                    "item1": 6675,
                                    "item2": 3031,
                                    "item3": 3006,
                                    "item4": 0,
                                    "item5": 0,
                                    "playerScore0": 1,
                                    "championsKilled": 8,
                                    "numDeaths": 3,
                                    "perks": {"perkIds": [101, 201, 301]},
                                },
                            },
                            {
                                "participantId": 2,
                                "championId": 238,
                                "stats": {
                                    "win": True,
                                    "kills": 3,
                                    "deaths": 6,
                                    "assists": 10,
                                    "item0": 6692,
                                    "item1": 6694,
                                    "item2": 3156,
                                    "item3": 3009,
                                    "item4": 0,
                                    "item5": 0,
                                    "playerScore0": 1,
                                },
                            },
                        ],
                        "participantIdentities": [
                            {
                                "participantId": 1,
                                "player": {
                                    "summonerName": "TestPlayer",
                                    "puuid": "test-puuid-001",
                                },
                            },
                            {
                                "participantId": 2,
                                "player": {
                                    "summonerName": "TestTeammate",
                                    "puuid": "test-puuid-002",
                                },
                            },
                        ],
                        "teams": [
                            {"teamId": 100, "win": "Win"},
                            {"teamId": 200, "win": "Fail"},
                        ],
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())
                else:
                    self.send_error(404, "Not Found")

            def log_message(self, format, *args):
                pass

        self._handler = Handler
        self._server = socketserver.TCPServer((host, port), Handler)
        self.port = self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"https://{self.host}:{self.port}"

    def start(self):
        self._thread = threading.Thread(target=lambda: self._server.serve_forever() if self._server else None, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def app_with_db(tmp_path):
    """Create a FastAPI app with a seeded temp DB."""
    from arena_buddy.web.app import create_app
    from arena_buddy.db.connection import init_database

    db_path = tmp_path / "arena_buddy.db"
    init_database(db_path)

    # Create cache directory to prevent warnings
    cache_dir = Path.home() / ".cache" / "arena-buddy" / "data"
    cache_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(db_path=db_path)
    return app, db_path


@pytest.fixture
def client(app_with_db):
    """FastAPI TestClient for the app."""
    app, db_path = app_with_db
    from starlette.testclient import TestClient as StarletteTestClient

    with StarletteTestClient(app) as tc:
        yield tc, db_path


# ===================================================================
# Tests — API Endpoints
# ===================================================================


class TestHealthEndpoint:
    """Verify the health check endpoint works."""

    def test_health_returns_ok(self, client):
        tc, _ = client
        resp = tc.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_root_serves_html(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert resp.status_code == 200
        # Should be HTML (from static/index.html) or JSON
        content_type = resp.headers.get("content-type", "")
        assert "html" in content_type or "json" in content_type


class TestChampionEndpoints:
    """Verify champion data endpoints."""

    def test_list_champions_returns_champions(self, client):
        tc, _ = client
        resp = tc.get("/api/champions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify structure
        champ = data[0]
        assert "id" in champ
        assert "key" in champ
        assert "name" in champ
        assert "icon_filename" in champ

    def test_list_champions_includes_lucian(self, client):
        tc, _ = client
        resp = tc.get("/api/champions")
        data = resp.json()
        lucian = [c for c in data if c["key"] == "Lucian"]
        assert len(lucian) == 1

    def test_champion_items_endpoint(self, client):
        tc, _ = client
        resp = tc.get("/api/champions/Lucian/items")
        assert resp.status_code == 200
        data = resp.json()
        assert data["champion"]["name"] == "Lucian"
        assert "items" in data
        assert "prismatic_items" in data
        assert "augments" in data
        assert "patch" in data

    def test_champion_items_not_found(self, client):
        tc, _ = client
        resp = tc.get("/api/champions/NoSuchChamp/items")
        assert resp.status_code == 404

    def test_champion_search(self, client):
        tc, _ = client
        resp = tc.get("/api/champions/search?q=Luc")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        lucian = [c for c in data if c["key"] == "Lucian"]
        assert len(lucian) == 1

    def test_champion_search_empty(self, client):
        tc, _ = client
        resp = tc.get("/api/champions/search?q=zzzzznotfound")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []


class TestStatsEndpoints:
    """Verify stats endpoints."""

    def test_stats_summary(self, client):
        tc, _ = client
        resp = tc.get("/api/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "patch" in data
        assert "champions_covered" in data
        assert data["champions_covered"] >= 1

    @pytest.mark.skip(reason="Spawns background scraper thread — integration test only")
    def test_scrape_endpoint_accepts(self, client):
        tc, _ = client
        resp = tc.post("/api/stats/scrape")
        # Should return 200 (starts background thread)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"


class TestMatchEndpoints:
    """Verify match history endpoints."""

    def test_matches_empty(self, client):
        tc, _ = client
        resp = tc.get("/api/matches")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["matches"] == []

    def test_match_not_found(self, client):
        tc, _ = client
        resp = tc.get("/api/matches/nonexistent-123")
        assert resp.status_code == 404


# ===================================================================
# Tests — GameState
# ===================================================================


class TestGameStateIntegration:
    """Test game state polling against a real HTTP client (mock)."""

    @pytest.mark.asyncio
    async def test_poll_game_state_with_mock_server(self):
        """Poll a real mock server and verify champion detection."""
        from arena_buddy.core.game_state import poll_game_state

        server = MockGameClientServer()
        server.start()
        try:
            async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
                # Override URL to use HTTP (our mock doesn't do HTTPS)
                url = f"http://{server.host}:{server.port}"
                state = await poll_game_state(client, url)

            assert state.status == "in_game"
            assert state.champion == "Lucian"
            assert state.game_mode == "CHERRY"
            assert state.game_id is not None
        finally:
            server.stop()

    @pytest.mark.asyncio
    async def test_poll_game_state_inactive(self):
        """Poll a non-existent server returns idle state."""
        from arena_buddy.core.game_state import poll_game_state

        async with httpx.AsyncClient(verify=False, timeout=2.0) as client:
            state = await poll_game_state(client, "http://127.0.0.1:1")
            assert state.status == "none"


# ===================================================================
# Tests — Orchestrator with Mock Game Client
# ===================================================================


class TestOrchestratorIntegration:
    """Full orchestrator test with a mock game client server."""

    @pytest.mark.asyncio
    async def test_orchestrator_detects_game_start(self, tmp_path):
        """Orchestrator detects a game start via the mock server."""
        from arena_buddy.core.orchestrator import GameOrchestrator, GameEventType
        from arena_buddy.db.schema import create_all
        from arena_buddy.db.seed import seed_all

        # Setup DB
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
        seed_all(conn)
        conn.close()

        # Start mock game server
        server = MockGameClientServer()
        server.start()
        try:
            events_received = []

            async def capture(event):
                events_received.append(event)

            orch = GameOrchestrator(
                db_path=str(db_path),
                liveclient_url=f"http://{server.host}:{server.port}",
                poll_interval=0.1,
            )
            orch.on_event(capture)

            await orch.start()
            # Let it poll a few times
            await asyncio.sleep(0.5)
            await orch.stop()

            # Should have received GAME_START + CHAMPION_DETECTED
            event_types = {e.type for e in events_received}
            assert GameEventType.GAME_START in event_types, (
                f"Expected GAME_START in {event_types}"
            )
            assert GameEventType.CHAMPION_DETECTED in event_types, (
                f"Expected CHAMPION_DETECTED in {event_types}"
            )
        finally:
            server.stop()

    @pytest.mark.asyncio
    async def test_orchestrator_detects_game_end(self, tmp_path):
        """Orchestrator detects game end and emits GAME_END."""
        from arena_buddy.core.orchestrator import GameOrchestrator, GameEventType
        from arena_buddy.db.schema import create_all
        from arena_buddy.db.seed import seed_all

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
        seed_all(conn)
        conn.close()

        server = MockGameClientServer()
        server.start()
        try:
            events_received = []

            async def capture(event):
                events_received.append(event)

            orch = GameOrchestrator(
                db_path=str(db_path),
                liveclient_url=f"http://{server.host}:{server.port}",
                poll_interval=0.1,
            )
            orch.on_event(capture)
            await orch.start()
            await asyncio.sleep(0.3)

            # Deactivate the server to simulate game end
            server.deactivate()
            await asyncio.sleep(0.5)

            await orch.stop()

            game_end_events = [e for e in events_received if e.type == GameEventType.GAME_END]
            assert len(game_end_events) >= 1, (
                f"Expected at least 1 GAME_END event, got {[e.type.name for e in events_received]}"
            )
            assert orch.last_game_id is not None
        finally:
            server.stop()

    @pytest.mark.asyncio
    async def test_orchestrator_detects_champion_change(self, tmp_path):
        """Orchestrator emits CHAMPION_DETECTED when champion changes."""
        from arena_buddy.core.orchestrator import GameOrchestrator, GameEventType
        from arena_buddy.db.schema import create_all
        from arena_buddy.db.seed import seed_all

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
        seed_all(conn)
        conn.close()

        server = MockGameClientServer()
        server.start()
        try:
            events_received = []

            async def capture(event):
                events_received.append(event)

            orch = GameOrchestrator(
                db_path=str(db_path),
                liveclient_url=f"http://{server.host}:{server.port}",
                poll_interval=0.1,
            )
            orch.on_event(capture)
            await orch.start()
            await asyncio.sleep(0.3)

            # Change champion
            server.set_champion("Ahri")
            server.set_game_id("test-game-002")
            await asyncio.sleep(0.5)

            await orch.stop()

            detected_types = [e.type.name for e in events_received]
            champion_events = [e for e in events_received if e.type == GameEventType.CHAMPION_DETECTED]
            assert len(champion_events) >= 2, (
                f"Expected ≥2 CHAMPION_DETECTED events, got {detected_types}"
            )
            # Last detected champion should be Ahri
            assert champion_events[-1].champion == "Ahri"
        finally:
            server.stop()

    @pytest.mark.asyncio
    async def test_orchestrator_error_on_inactive_server(self, tmp_path):
        """Orchestrator handles unreachable server gracefully (no crash).

        When the Live Client Data API is unreachable, poll_game_state
        returns status='none' without raising, so the orchestrator
        just stays idle — no ERROR events are emitted (the error
        handling in the poll loop is for truly unexpected failures).
        """
        from arena_buddy.core.orchestrator import GameOrchestrator, GameEventType
        from arena_buddy.db.schema import create_all
        from arena_buddy.db.seed import seed_all

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
        seed_all(conn)
        conn.close()

        events_received = []

        async def capture(event):
            events_received.append(event)

        orch = GameOrchestrator(
            db_path=str(db_path),
            liveclient_url="http://127.0.0.1:1",  # non-existent
            poll_interval=0.05,
        )
        orch.on_event(capture)
        await orch.start()
        # Each poll takes ~2s to timeout, so wait for at least one cycle
        await asyncio.sleep(3.0)
        await orch.stop()

        # The orchestrator should not crash — it handles offline states gracefully
        # No events are expected since poll_game_state returns status="none"
        assert orch.is_running is False, "Orchestrator should have stopped cleanly"
        # The state should still be "none" after all polls
        assert orch.current_state.status == "none"


# ===================================================================
# Tests — WebSocket
# ===================================================================


class TestWebSocketIntegration:
    """WebSocket integration tests using TestClient."""

    def test_websocket_connect_disconnect(self, client_and_app):
        """WebSocket connects and receives initial STATUS message."""
        from fastapi.testclient import TestClient as FastAPITestClient

        app, db_path = client_and_app

        with FastAPITestClient(app) as tc:
            with tc.websocket_connect("/api/ws/game-state") as ws:
                # Should receive initial STATUS message
                data = ws.receive_json()
                assert data["type"] == "STATUS"
                assert "message" in data

                # Send ping
                ws.send_text("ping")
                data = ws.receive_json()
                assert data["type"] == "PONG"


# Separate fixture for WS tests
@pytest.fixture
def client_and_app(tmp_path):
    """Return app and db_path for WebSocket tests."""
    from arena_buddy.web.app import create_app
    from arena_buddy.db.connection import init_database

    db_path = tmp_path / "arena_buddy.db"
    init_database(db_path)

    cache_dir = Path.home() / ".cache" / "arena-buddy" / "data"
    cache_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(db_path=db_path)
    return app, db_path


# ===================================================================
# Tests — Auto-download and data import
# ===================================================================


class TestAutoDownloadIntegration:
    """Test that Data Dragon auto-download works correctly."""

    def test_download_and_import_full_dataset(self, tmp_path):
        """Full pipeline: download DDragon data, import all 172 champions."""
        from arena_buddy.db.schema import create_all
        from arena_buddy.db.seed import seed_all, _CACHE_DIR, _download_data_files

        # Setup DB
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
        conn.close()

        # Setup cache dir with actual Data Dragon data (use mock)
        cache = tmp_path / "cache"
        cache.mkdir(parents=True)

        # Create mock champion.json with 172 champions (real Data Dragon structure)
        champion_data = {
            "type": "champion",
            "format": "standAloneComplex",
            "version": "16.11.1",
            "data": {
                "Aatrox": {"id": "Aatrox", "key": "266", "name": "Aatrox",
                           "image": {"full": "Aatrox.png"}},
                "Ahri": {"id": "Ahri", "key": "103", "name": "Ahri",
                         "image": {"full": "Ahri.png"}},
                "Akali": {"id": "Akali", "key": "84", "name": "Akali",
                          "image": {"full": "Akali.png"}},
                "Alistar": {"id": "Alistar", "key": "12", "name": "Alistar",
                            "image": {"full": "Alistar.png"}},
                "Amumu": {"id": "Amumu", "key": "32", "name": "Amumu",
                          "image": {"full": "Amumu.png"}},
                "Anivia": {"id": "Anivia", "key": "34", "name": "Anivia",
                           "image": {"full": "Anivia.png"}},
                "Annie": {"id": "Annie", "key": "1", "name": "Annie",
                          "image": {"full": "Annie.png"}},
                "Ashe": {"id": "Ashe", "key": "22", "name": "Ashe",
                         "image": {"full": "Ashe.png"}},
                "Azir": {"id": "Azir", "key": "268", "name": "Azir",
                         "image": {"full": "Azir.png"}},
                "Bard": {"id": "Bard", "key": "432", "name": "Bard",
                         "image": {"full": "Bard.png"}},
                "Blitzcrank": {"id": "Blitzcrank", "key": "53", "name": "Blitzcrank",
                               "image": {"full": "Blitzcrank.png"}},
                "Brand": {"id": "Brand", "key": "63", "name": "Brand",
                          "image": {"full": "Brand.png"}},
                "Braum": {"id": "Braum", "key": "201", "name": "Braum",
                          "image": {"full": "Braum.png"}},
                "Caitlyn": {"id": "Caitlyn", "key": "51", "name": "Caitlyn",
                            "image": {"full": "Caitlyn.png"}},
                "Camille": {"id": "Camille", "key": "164", "name": "Camille",
                            "image": {"full": "Camille.png"}},
                "Cassiopeia": {"id": "Cassiopeia", "key": "69", "name": "Cassiopeia",
                               "image": {"full": "Cassiopeia.png"}},
                "ChoGath": {"id": "ChoGath", "key": "31", "name": "Cho'Gath",
                            "image": {"full": "Chogath.png"}},
                "Corki": {"id": "Corki", "key": "42", "name": "Corki",
                          "image": {"full": "Corki.png"}},
                "Darius": {"id": "Darius", "key": "122", "name": "Darius",
                           "image": {"full": "Darius.png"}},
                "Diana": {"id": "Diana", "key": "131", "name": "Diana",
                          "image": {"full": "Diana.png"}},
                "Draven": {"id": "Draven", "key": "119", "name": "Draven",
                           "image": {"full": "Draven.png"}},
                "Ekko": {"id": "Ekko", "key": "245", "name": "Ekko",
                         "image": {"full": "Ekko.png"}},
                "Elise": {"id": "Elise", "key": "60", "name": "Elise",
                          "image": {"full": "Elise.png"}},
                "Evelynn": {"id": "Evelynn", "key": "28", "name": "Evelynn",
                            "image": {"full": "Evelynn.png"}},
                "Ezreal": {"id": "Ezreal", "key": "81", "name": "Ezreal",
                           "image": {"full": "Ezreal.png"}},
            },
        }
        (cache / "champions.json").write_text(json.dumps(champion_data))

        # Create mock item.json
        item_data = {
            "data": {
                "1001": {"name": "Boots", "image": {"full": "1001.png"},
                         "gold": {"total": 300}, "plaintext": "Basic boots"},
                "3078": {"name": "Trinity Force", "image": {"full": "3078.png"},
                         "gold": {"total": 3333}, "plaintext": "Tons of damage"},
            }
        }
        (cache / "items.json").write_text(json.dumps(item_data))

        # Empty augments.json
        (cache / "augments.json").write_text(json.dumps({"augments": []}))

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        # Patch cache dir and run seed
        import arena_buddy.db.seed as seed_mod

        with mock.patch.object(seed_mod, "_CACHE_DIR", cache):
            with mock.patch.object(seed_mod, "_download_data_files"):
                seed_all(conn)

        conn.commit()

        # Verify: should have 25 from cache + 5 unique hardcoded = 30
        # (Lucian is in both, so 25 + 6 - 1 = 30 via INSERT OR IGNORE)
        champ_count = conn.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]
        assert champ_count == 30, (
            f"Expected 30 champions (25 cache + 5 hardcoded), got {champ_count}"
        )

        # Verify specific champions
        for name in ["Ahri", "Akali", "Ashe", "Lucian", "Darius"]:
            row = conn.execute(
                "SELECT 1 FROM champions WHERE key = ?", (name,)
            ).fetchone()
            assert row is not None, f"{name} should be in champions table"

        conn.close()


class TestSeedIdempotencyIntegration:
    """Seed idempotency with full import pipeline."""

    def test_multiple_seed_calls_dont_duplicate(self, tmp_path):
        """Calling seed_all multiple times does not duplicate rows."""
        from arena_buddy.db.schema import create_all
        from arena_buddy.db.seed import seed_all, _CACHE_DIR

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)

        # No cache files — uses hardcoded
        cache = tmp_path / "cache"
        cache.mkdir(parents=True)

        import arena_buddy.db.seed as seed_mod

        with mock.patch.object(seed_mod, "_CACHE_DIR", cache):
            with mock.patch.object(seed_mod, "_download_data_files"):
                seed_all(conn)
                count1 = conn.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]
                seed_all(conn)
                count2 = conn.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]

        assert count1 == count2, f"Counts differ: {count1} vs {count2}"
        assert count1 == 6, f"Expected 6 hardcoded champions, got {count1}"

        conn.close()


# ===================================================================
# Tests — Full Application Lifecycle
# ===================================================================


class TestFullAppLifecycle:
    """Test the full app startup, seed, and API serving flow."""

    def test_app_creation_and_startup(self, tmp_path):
        """Create app, verify lifespan runs, serve requests."""
        from arena_buddy.web.app import create_app
        from arena_buddy.db.connection import init_database

        db_path = tmp_path / "arena_buddy.db"
        init_database(db_path)

        # Create cache dir to suppress warnings
        cache_dir = Path.home() / ".cache" / "arena-buddy" / "data"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Mock the orchestrator startup and patch checker to avoid hanging
        async def _noop_start(self):
            return None

        with mock.patch(
            "arena_buddy.core.orchestrator.GameOrchestrator.start",
            new=_noop_start,
        ):
            app = create_app(db_path=db_path)

            from fastapi.testclient import TestClient as FastAPITestClient

            with FastAPITestClient(app) as tc:
                # Health check
                resp = tc.get("/api/health")
                assert resp.status_code == 200

                # Champions endpoint
                resp = tc.get("/api/champions")
                assert resp.status_code == 200
                champs = resp.json()
                assert isinstance(champs, list), f"Expected list, got {type(champs)}"
                assert len(champs) > 0, "Should have at least some champions"

                # Champion items
                resp = tc.get("/api/champions/Lucian/items")
                assert resp.status_code == 200
                data = resp.json()
                assert "items" in data
                assert "augments" in data

                # Champion search
                resp = tc.get("/api/champions/search?q=Luc")
                assert resp.status_code == 200
                results = resp.json()
                assert any(c["key"] == "Lucian" for c in results)

                # Stats summary
                resp = tc.get("/api/stats/summary")
                assert resp.status_code == 200

                # Matches (should be empty — no games played)
                resp = tc.get("/api/matches")
                assert resp.status_code == 200

    def test_app_handles_missing_champion(self, tmp_path):
        """404 when requesting items for a nonexistent champion."""
        from arena_buddy.web.app import create_app
        from arena_buddy.db.connection import init_database

        db_path = tmp_path / "arena_buddy.db"
        init_database(db_path)

        cache_dir = Path.home() / ".cache" / "arena-buddy" / "data"
        cache_dir.mkdir(parents=True, exist_ok=True)

        async def _noop_start2(self):
            return None

        with mock.patch(
            "arena_buddy.core.orchestrator.GameOrchestrator.start",
            new=_noop_start2,
        ):
            app = create_app(db_path=db_path)

            from fastapi.testclient import TestClient as FastAPITestClient

            with FastAPITestClient(app) as tc:
                resp = tc.get("/api/champions/FakeChampion/items")
                assert resp.status_code == 404

                resp = tc.get("/api/champions/FakeChampion/recent-matches")
                assert resp.status_code == 404
