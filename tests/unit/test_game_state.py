"""Tests for arena_buddy.core.game_state — Game state poller."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from arena_buddy.core.game_state import (
    GameState,
    detect_game_end,
    detect_game_start,
    poll_game_state,
)


# ---------------------------------------------------------------------------
# Mock helpers — build realistic Live Client Data API responses
# ---------------------------------------------------------------------------

def _make_allgamedata(game_mode: str = "CHERRY") -> dict:
    """Build a minimal /allgamedata response."""
    return {
        "gameData": {
            "gameMode": game_mode,
            "gameId": "test-game-123",
        },
        "activePlayer": {
            "championStats": {},
            "summonerName": "TestPlayer",
            "championName": "Lucian",
            "abilities": {},
            "currentGold": 500.0,
            "level": 5,
        },
        "allPlayers": [],
        "events": {"Events": []},
    }


def _make_activeplayer(champion_name: str = "Lucian") -> dict:
    return {
        "championStats": {
            "abilityPower": 0.0,
            "armor": 50.0,
            "attackDamage": 80.0,
            "attackSpeed": 1.2,
            "currentHealth": 1000.0,
            "maxHealth": 1000.0,
            "magicResist": 30.0,
            "moveSpeed": 380.0,
            "resourceValue": 500.0,
            "resourceMax": 500.0,
            "resourceRegenRate": 2.0,
        },
        "summonerName": "TestPlayer",
        "championName": champion_name,
        "level": 6,
        "abilities": {},
        "currentGold": 800.0,
        "items": [],
        "runes": {},
        "summonerSpells": {},
    }


def _make_eventdata() -> dict:
    return {"Events": []}


# ---------------------------------------------------------------------------
# GameState tests (no HTTP needed)
# ---------------------------------------------------------------------------

class TestGameState:
    """Unit tests for the GameState dataclass."""

    def test_default_inactive(self) -> None:
        """Default GameState has 'none' status."""
        gs = GameState()
        assert gs.status == "none"
        assert gs.champion is None
        assert gs.game_mode is None
        assert gs.game_id is None

    def test_in_game_state(self) -> None:
        """Creating with in_game status stores fields."""
        gs = GameState(
            champion="Lucian",
            game_mode="CHERRY",
            game_id="12345",
            status="in_game",
        )
        assert gs.champion == "Lucian"
        assert gs.game_mode == "CHERRY"
        assert gs.game_id == "12345"
        assert gs.status == "in_game"

    def test_champ_select_state(self) -> None:
        """Champ select state has status but no champion yet."""
        gs = GameState(status="champ_select")
        assert gs.status == "champ_select"
        assert gs.champion is None

    def test_ended_state(self) -> None:
        """Ended state with final champion info."""
        gs = GameState(champion="Lucian", status="ended")
        assert gs.status == "ended"
        assert gs.champion == "Lucian"

    def test_equality(self) -> None:
        """Two GameStates with same fields are equal."""
        a = GameState(champion="Lucian", game_mode="CHERRY", status="in_game")
        b = GameState(champion="Lucian", game_mode="CHERRY", status="in_game")
        assert a == b

    def test_inequality(self) -> None:
        """Different fields mean inequality."""
        a = GameState(status="none")
        b = GameState(status="in_game")
        assert a != b


# ---------------------------------------------------------------------------
# State transition detection (unit tests — no HTTP)
# ---------------------------------------------------------------------------

class TestDetectGameStart:
    """Unit tests for game start detection logic."""

    def test_none_to_in_game_is_start(self) -> None:
        """Transition from 'none' to 'in_game' = game start."""
        prev = GameState(status="none")
        curr = GameState(status="in_game", game_mode="CHERRY")
        assert detect_game_start(prev, curr) is True

    def test_champ_select_to_in_game_is_start(self) -> None:
        """Transition from champ_select to in_game = game start."""
        prev = GameState(status="champ_select")
        curr = GameState(status="in_game", game_mode="CHERRY")
        assert detect_game_start(prev, curr) is True

    def test_in_game_to_in_game_not_start(self) -> None:
        """Staying in in_game is not a new start."""
        prev = GameState(status="in_game", game_mode="CHERRY")
        curr = GameState(status="in_game", game_mode="CHERRY")
        assert detect_game_start(prev, curr) is False

    def test_none_to_champ_select_not_start(self) -> None:
        """Champ select is a precursor, not game start."""
        prev = GameState(status="none")
        curr = GameState(status="champ_select")
        assert detect_game_start(prev, curr) is False

    def test_in_game_to_ended_not_start(self) -> None:
        """Game ending is not a new start."""
        prev = GameState(status="in_game", game_mode="CHERRY")
        curr = GameState(status="ended")
        assert detect_game_start(prev, curr) is False


class TestDetectGameEnd:
    """Unit tests for game end detection logic."""

    def test_in_game_to_ended_is_end(self) -> None:
        """Transition from in_game to ended = game end."""
        prev = GameState(status="in_game", game_mode="CHERRY")
        curr = GameState(status="ended", champion="Lucian")
        assert detect_game_end(prev, curr) is True

    def test_champ_select_to_ended_is_end(self) -> None:
        """Cancel / dodge transitions to ended."""
        prev = GameState(status="champ_select")
        curr = GameState(status="ended")
        assert detect_game_end(prev, curr) is True

    def test_none_to_none_not_end(self) -> None:
        """No transition at all is not a game end."""
        prev = GameState(status="none")
        curr = GameState(status="none")
        assert detect_game_end(prev, curr) is False

    def test_in_game_to_in_game_not_end(self) -> None:
        """Still playing is not an end."""
        prev = GameState(status="in_game", game_mode="CHERRY")
        curr = GameState(status="in_game", game_mode="CHERRY")
        assert detect_game_end(prev, curr) is False

    def test_none_to_in_game_not_end(self) -> None:
        """Starting is not ending."""
        prev = GameState(status="none")
        curr = GameState(status="in_game")
        assert detect_game_end(prev, curr) is False


# ---------------------------------------------------------------------------
# poll_game_state tests using mocked httpx
# ---------------------------------------------------------------------------

class TestPollGameState:
    """Integration-style tests for poll_game_state with mocked HTTP."""

    @pytest.fixture
    def mock_client(self) -> httpx.AsyncClient:
        """Create an httpx.AsyncClient with a mock transport."""
        transport = httpx.MockTransport(_mock_handler)
        return httpx.AsyncClient(transport=transport)

    @pytest.mark.asyncio
    async def test_poll_in_game_champion(self, mock_client: httpx.AsyncClient) -> None:
        """When API returns valid data, champion and game_mode are extracted."""
        result = await poll_game_state(mock_client, "https://127.0.0.1:2999/liveclientdata")
        assert result.status == "in_game"
        assert result.champion == "Lucian"
        assert result.game_mode == "CHERRY"
        assert result.game_id is not None

    @pytest.mark.asyncio
    async def test_poll_arena_mode_detected(self, mock_client: httpx.AsyncClient) -> None:
        """CHERRY game mode is detected as Arena."""
        result = await poll_game_state(mock_client, "https://127.0.0.1:2999/liveclientdata")
        assert result.game_mode == "CHERRY"

    @pytest.mark.asyncio
    async def test_poll_connection_refused_yields_none(self) -> None:
        """When the Live Client Data API is unreachable, status='none'."""
        transport = httpx.MockTransport(_refused_handler)
        client = httpx.AsyncClient(transport=transport)
        result = await poll_game_state(client, "https://127.0.0.1:2999/liveclientdata")
        assert result.status == "none"
        assert result.champion is None
        assert result.game_mode is None

    @pytest.mark.asyncio
    async def test_poll_timeout_yields_none(self) -> None:
        """Timeout means no game running."""
        transport = httpx.MockTransport(_timeout_handler)
        client = httpx.AsyncClient(transport=transport)
        result = await poll_game_state(client, "https://127.0.0.1:2999/liveclientdata")
        assert result.status == "none"

    @pytest.mark.asyncio
    async def test_poll_http_error_yields_none(self) -> None:
        """Non-200 status is treated as no game."""
        transport = httpx.MockTransport(_error_handler)
        client = httpx.AsyncClient(transport=transport)
        result = await poll_game_state(client, "https://127.0.0.1:2999/liveclientdata")
        assert result.status == "none"

    @pytest.mark.asyncio
    async def test_poll_invalid_json_yields_none(self) -> None:
        """Malformed JSON means no game data."""
        transport = httpx.MockTransport(_invalid_json_handler)
        client = httpx.AsyncClient(transport=transport)
        result = await poll_game_state(client, "https://127.0.0.1:2999/liveclientdata")
        assert result.status == "none"

    @pytest.mark.asyncio
    async def test_poll_classic_mode_detected(self) -> None:
        """Non-CHERRY game mode: CLASSIC etc. still reported."""
        transport = httpx.MockTransport(_classic_handler)
        client = httpx.AsyncClient(transport=transport)
        result = await poll_game_state(client, "https://127.0.0.1:2999/liveclientdata")
        assert result.game_mode == "CLASSIC"
        assert result.status == "in_game"


# ---------------------------------------------------------------------------
# Mock transport handlers
# ---------------------------------------------------------------------------

def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Simulate a running Live Client Data API."""
    url = str(request.url)
    if "allgamedata" in url:
        data = _make_allgamedata(game_mode="CHERRY")
    elif "activeplayer" in url:
        data = _make_activeplayer(champion_name="Lucian")
    elif "eventdata" in url:
        data = _make_eventdata()
    else:
        # Root endpoint: return combined info
        data = {
            "allgamedata": _make_allgamedata(game_mode="CHERRY"),
            "activeplayer": _make_activeplayer(champion_name="Lucian"),
            "eventdata": _make_eventdata(),
        }
    return httpx.Response(200, json=data)


def _classic_handler(request: httpx.Request) -> httpx.Response:
    """Simulate Classic (SR) game."""
    data = _make_allgamedata(game_mode="CLASSIC")
    data["activePlayer"]["championName"] = "Lucian"
    return httpx.Response(200, json=data)


def _refused_handler(request: httpx.Request) -> httpx.Response:
    """Simulate connection refused."""
    import socket
    raise httpx.ConnectError("Connection refused")


def _timeout_handler(request: httpx.Request) -> httpx.Response:
    """Simulate timeout."""
    raise httpx.TimeoutException("Request timed out")


def _error_handler(request: httpx.Request) -> httpx.Response:
    """Simulate HTTP 500 error."""
    return httpx.Response(500, text="Internal Server Error")


def _invalid_json_handler(request: httpx.Request) -> httpx.Response:
    """Simulate invalid JSON response."""
    return httpx.Response(200, content=b"not json {{{")
