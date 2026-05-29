"""Tests for arena_buddy.core.orchestrator — Game polling orchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from arena_buddy.core.game_state import GameState
from arena_buddy.core.orchestrator import (
    GameOrchestrator,
    GameEvent,
    GameEventType,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_db(tmp_path):
    """Create an empty SQLite DB with schema for testing."""
    import sqlite3
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    from arena_buddy.db.schema import create_all
    from arena_buddy.db.seed import seed_all
    create_all(conn)
    seed_all(conn)
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# GameEvent dataclass tests
# ---------------------------------------------------------------------------


class TestGameEvent:
    def test_event_creation(self):
        """GameEvent can be created with all fields."""
        event = GameEvent(
            type=GameEventType.GAME_START,
            champion="Lucian",
            game_mode="CHERRY",
            game_id="test-123",
        )
        assert event.type == GameEventType.GAME_START
        assert event.champion == "Lucian"
        assert event.game_mode == "CHERRY"
        assert event.game_id == "test-123"

    def test_event_full_details(self):
        """GameEvent serializes with full_details dict."""
        event = GameEvent(
            type=GameEventType.GAME_END,
            champion="Zed",
            game_mode="CHERRY",
            game_id="match-456",
        )
        details = event.full_details
        assert details["game_id"] == "match-456"
        assert details["champion"] == "Zed"

    def test_event_types_are_distinct(self):
        """Each event type is uniquely identifiable."""
        types = set(GameEventType)
        assert len(types) == 6  # GAME_START, GAME_END, CHAMPION_DETECTED, STATUS, IDLE, ERROR


# ---------------------------------------------------------------------------
# GameOrchestrator game detection tests
# ---------------------------------------------------------------------------


class TestOrchestratorGameDetection:
    """Tests for the orchestrator's game state detection logic."""

    def test_is_arena_game_cherry(self):
        """CHERRY mode is recognized as Arena."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        state = GameState(champion="Lucian", game_mode="CHERRY", status="in_game")
        assert orch._is_arena_game(state) is True

    def test_is_arena_game_classic(self):
        """CLASSIC mode is NOT arena (Summoner's Rift)."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        state = GameState(champion="Lucian", game_mode="CLASSIC", status="in_game")
        assert orch._is_arena_game(state) is False

    def test_is_arena_game_none(self):
        """None game mode is not Arena."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        state = GameState(champion="Lucian", game_mode=None, status="in_game")
        assert orch._is_arena_game(state) is False

    def test_detect_game_start_transition(self):
        """Orchestrator detects transition from idle to in_game."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        prev = GameState(status="none")
        curr = GameState(champion="Lucian", game_mode="CHERRY", status="in_game")

        events = orch._check_transition(prev, curr)
        assert len(events) == 1
        assert events[0].type == GameEventType.GAME_START
        assert events[0].champion == "Lucian"

    def test_no_event_on_same_state(self):
        """No event emitted when state hasn't changed."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        state = GameState(champion="Lucian", game_mode="CHERRY", status="in_game")
        events = orch._check_transition(state, state)  # same state
        assert len(events) == 0

    def test_detect_game_end_transition(self):
        """Orchestrator detects transition from in_game to none (game ended)."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        prev = GameState(
            champion="Lucian", game_mode="CHERRY", status="in_game", game_id="match-123"
        )
        curr = GameState(status="none")
        events = orch._check_transition(prev, curr)
        assert events[-1].type == GameEventType.GAME_END
        assert orch.last_game_id == "match-123"

    def test_no_game_end_for_non_arena(self):
        """No game-end event for non-Arena games."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        prev = GameState(
            champion="Lucian", game_mode="CLASSIC", status="in_game", game_id="sr-123"
        )
        curr = GameState(status="none")
        events = orch._check_transition(prev, curr)
        assert len(events) == 0
        assert orch.last_game_id is None  # not set for non-Arena


# ---------------------------------------------------------------------------
# Callback tests
# ---------------------------------------------------------------------------


class TestOrchestratorCallbacks:
    """Tests for the event callback system."""

    @pytest.mark.asyncio
    async def test_register_callback(self):
        """Callbacks can be registered and receive events."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        received = []

        async def cb(event):
            received.append(event)

        orch.on_event(cb)
        event = GameEvent(type=GameEventType.STATUS, message="test")
        await orch.emit(event)
        assert len(received) == 1
        assert received[0].message == "test"

    @pytest.mark.asyncio
    async def test_register_multiple_callbacks(self):
        """Multiple callbacks all receive the same event."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        results = [[], []]

        async def cb0(event):
            results[0].append(event)

        async def cb1(event):
            results[1].append(event)

        orch.on_event(cb0)
        orch.on_event(cb1)

        event = GameEvent(type=GameEventType.STATUS, message="multi")
        await orch.emit(event)
        assert len(results[0]) == 1
        assert len(results[1]) == 1

    def test_remove_callback(self):
        """Callbacks can be removed (sync — emit not called, just registration)."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        received = []

        async def cb(event):
            received.append(event)

        unsub = orch.on_event(cb)
        unsub()
        assert len(orch._callbacks) == 0


class TestOrchestratorLifecycle:
    """Tests for start/stop and state management."""

    def test_initial_state_is_idle(self):
        """Orchestrator starts in idle state."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        assert orch.is_running is False

    def test_get_current_game_state(self):
        """Can retrieve the current known game state."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        initial = orch.current_state
        assert initial.status == "none"
        assert initial.champion is None

    def test_last_game_details_persist_after_end(self):
        """After a game ends, last_game_id and last_game_mode are available."""
        orch = GameOrchestrator(db_path="/tmp/fake.db")
        prev = GameState(
            champion="Zed", game_mode="CHERRY", status="in_game", game_id="m456"
        )
        curr = GameState(status="none")
        orch._check_transition(prev, curr)
        assert orch.last_game_id == "m456"
        assert orch.last_game_mode == "CHERRY"

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self):
        """Orchestrator can be started and stopped."""
        orch = GameOrchestrator(
            db_path="/tmp/fake.db",
            liveclient_url="https://127.0.0.1:1/invalid",  # fast-fail URL
            poll_interval=0.1,
        )
        assert not orch.is_running

        # Start (will fail quickly since the URL is unreachable, but
        # the task is created)
        await orch.start()
        assert orch.is_running

        # Stop
        await orch.stop()
        assert not orch.is_running
