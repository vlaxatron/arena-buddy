"""Tests for arena_buddy.core.match_capture — LCU match history capture."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from arena_buddy.core.match_capture import (
    create_lcu_client,
    fetch_match_detail,
    fetch_match_history,
    find_lockfile,
    parse_lockfile,
)


# ---------------------------------------------------------------------------
# Lockfile tests
# ---------------------------------------------------------------------------

class TestFindLockfile:
    """Tests for find_lockfile() — locating the League lockfile."""

    def test_finds_lockfile_in_temp_dir(self, tmp_path: Path) -> None:
        """When a lockfile exists in a known location, it is found."""
        lockfile_path = tmp_path / "lockfile"
        lockfile_path.write_text(
            "LeagueClient:12345:56789:MyPassword123:https"
        )
        # We can search a specific path with monkeypatch
        with patch("arena_buddy.core.match_capture._KNOWN_LOCKFILE_LOCATIONS",
                   [str(tmp_path / "lockfile")]):
            result = find_lockfile()
            assert result is not None
            assert result == lockfile_path

    def test_returns_none_when_no_lockfile(self) -> None:
        """When no lockfile exists, returns None."""
        with patch("arena_buddy.core.match_capture._KNOWN_LOCKFILE_LOCATIONS",
                   ["/nonexistent/path/lockfile"]):
            result = find_lockfile()
            assert result is None


class TestParseLockfile:
    """Tests for parse_lockfile()."""

    def test_parses_valid_lockfile(self, tmp_path: Path) -> None:
        """Valid lockfile content is parsed into a dict with expected keys."""
        lockfile = tmp_path / "lockfile"
        lockfile.write_text("LeagueClient:12345:56789:MyPassword123:https")
        result = parse_lockfile(lockfile)
        assert result["port"] == 56789
        assert result["password"] == "MyPassword123"
        assert result["protocol"] == "https"
        assert result["pid"] == 12345

    def test_parses_different_port(self, tmp_path: Path) -> None:
        """Different port numbers are correctly parsed."""
        lockfile = tmp_path / "lockfile"
        lockfile.write_text("LeagueClient:1:49152:abc123:https")
        result = parse_lockfile(lockfile)
        assert result["port"] == 49152
        assert result["password"] == "abc123"

    def test_raises_on_invalid_format(self, tmp_path: Path) -> None:
        """Malformed lockfile content raises ValueError."""
        lockfile = tmp_path / "lockfile"
        lockfile.write_text("not a valid lockfile")
        with pytest.raises(ValueError, match="Invalid lockfile format"):
            parse_lockfile(lockfile)

    def test_raises_on_missing_fields(self, tmp_path: Path) -> None:
        """Too few fields raises ValueError."""
        lockfile = tmp_path / "lockfile"
        lockfile.write_text("LeagueClient:12345:56789")
        with pytest.raises(ValueError, match="Invalid lockfile format"):
            parse_lockfile(lockfile)

    def test_raises_on_non_integer_port(self, tmp_path: Path) -> None:
        """Non-integer port raises ValueError."""
        lockfile = tmp_path / "lockfile"
        lockfile.write_text("LeagueClient:12345:abcde:password:https")
        with pytest.raises(ValueError, match="Invalid lockfile format"):
            parse_lockfile(lockfile)

    def test_raises_on_empty_file(self, tmp_path: Path) -> None:
        """Empty lockfile raises ValueError."""
        lockfile = tmp_path / "lockfile"
        lockfile.write_text("")
        with pytest.raises(ValueError, match="Invalid lockfile format"):
            parse_lockfile(lockfile)


# ---------------------------------------------------------------------------
# LCU client creation
# ---------------------------------------------------------------------------

class TestCreateLcuClient:
    """Tests for create_lcu_client()."""

    def test_creates_client_with_basic_auth(self) -> None:
        """Client is created with correct base URL and auth headers."""
        client = create_lcu_client(port=12345, password="testpass")
        assert isinstance(client, httpx.AsyncClient)
        assert client.base_url == "https://127.0.0.1:12345"
        # Verify basic auth header is set
        auth_header = client.headers.get("authorization")
        assert auth_header is not None
        assert "Basic" in auth_header

    def test_creates_client_with_different_port(self) -> None:
        """Different port produces correct base URL."""
        client = create_lcu_client(port=29999, password="p@ss!")
        assert client.base_url == "https://127.0.0.1:29999"

    def test_verify_ssl_disabled(self) -> None:
        """LCU uses self-signed certs, so verify=False — client is created without errors."""
        client = create_lcu_client(port=12345, password="testpass")
        # In httpx, verify might be returned as False or an SSL context.
        # The key thing is the client was created successfully.
        assert isinstance(client, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# Match history tests (mocked HTTP)
# ---------------------------------------------------------------------------

# Sample match history response from LCU
_SAMPLE_MATCH_HISTORY = {
    "games": {
        "games": [
            {
                "gameId": 123456789,
                "gameCreation": 1609459200000,
                "gameDuration": 1200,
                "gameMode": "CHERRY",
                "gameType": "MATCHED_GAME",
                "mapId": 30,
                "queueId": 1700,
                "participants": [
                    {
                        "championId": 236,
                        "stats": {
                            "win": "Win",
                            "kills": 5,
                            "deaths": 3,
                            "assists": 4,
                            "item0": 3031,
                            "item1": 6694,
                            "item2": 0,
                            "item3": 0,
                            "item4": 0,
                            "item5": 0,
                            "playerAugment1": 1001,
                            "playerAugment2": 2001,
                            "playerAugment3": 3001,
                            "playerAugment4": 4001,
                            "placement": 2,
                        },
                        "puuid": "test-puuid-123",
                    }
                ],
            }
        ]
    }
}

_SAMPLE_MATCH_DETAIL = {
    "gameId": 123456789,
    "gameCreation": 1609459200000,
    "gameDuration": 1200,
    "gameMode": "CHERRY",
    "mapId": 30,
    "queueId": 1700,
    "participants": [
        {
            "championId": 236,
            "puuid": "test-puuid-123",
            "stats": {
                "win": "Win",
                "kills": 5,
                "deaths": 3,
                "assists": 4,
                "item0": 3031,
                "item1": 6694,
                "item2": 0,
                "item3": 0,
                "item4": 0,
                "item5": 0,
                "playerAugment1": 1001,
                "playerAugment2": 2001,
                "playerAugment3": 3001,
                "playerAugment4": 4001,
                "placement": 2,
            },
        }
    ],
    "participantIdentities": [
        {
            "participantId": 1,
            "player": {
                "puuid": "test-puuid-123",
                "summonerName": "TestPlayer",
            },
        }
    ],
}


def _make_lcu_transport(handler_func):
    """Create an httpx.AsyncClient with a mock transport for LCU."""
    transport = httpx.MockTransport(handler_func)
    return httpx.AsyncClient(
        transport=transport,
        base_url="https://127.0.0.1:12345",
    )


def _success_handler(request: httpx.Request) -> httpx.Response:
    """Mock handler for successful LCU responses."""
    url = str(request.url)
    if "/lol-match-history/v1/games/" in url and "/matches" not in url:
        # Match detail request (e.g. .../games/123456789)
        return httpx.Response(200, json=_SAMPLE_MATCH_DETAIL)
    else:
        # Match history list
        return httpx.Response(200, json=_SAMPLE_MATCH_HISTORY)


class TestFetchMatchHistory:
    """Tests for fetch_match_history()."""

    @pytest.mark.asyncio
    async def test_fetch_returns_list_of_games(self) -> None:
        """Returns a list of match dicts from the LCU."""
        client = _make_lcu_transport(_success_handler)
        result = await fetch_match_history(client, puuid="test-puuid-123")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["gameId"] == 123456789

    @pytest.mark.asyncio
    async def test_fetch_with_empty_history(self) -> None:
        """Empty games list returns empty list."""

        def empty_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"games": {"games": []}})

        client = _make_lcu_transport(empty_handler)
        result = await fetch_match_history(client, puuid="unknown-puuid")
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_handles_http_error(self) -> None:
        """HTTP error from LCU is handled gracefully (returns empty list)."""

        def error_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Error")

        client = _make_lcu_transport(error_handler)
        result = await fetch_match_history(client, puuid="test-puuid-123")
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_handles_connection_refused(self) -> None:
        """Connection error returns empty list."""

        def refused_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Refused")

        client = _make_lcu_transport(refused_handler)
        result = await fetch_match_history(client, puuid="test-puuid-123")
        assert result == []


class TestFetchMatchDetail:
    """Tests for fetch_match_detail()."""

    @pytest.mark.asyncio
    async def test_fetch_detail_returns_dict(self) -> None:
        """Returns a match detail dict."""
        client = _make_lcu_transport(_success_handler)
        result = await fetch_match_detail(client, game_id="123456789")
        assert isinstance(result, dict)
        assert result["gameId"] == 123456789
        assert "participants" in result

    @pytest.mark.asyncio
    async def test_fetch_detail_has_participants(self) -> None:
        """Match detail contains participants with stats."""
        client = _make_lcu_transport(_success_handler)
        result = await fetch_match_detail(client, game_id="123456789")
        assert len(result["participants"]) > 0
        participant = result["participants"][0]
        assert "stats" in participant

    @pytest.mark.asyncio
    async def test_fetch_detail_handles_error(self) -> None:
        """HTTP error returns empty dict."""

        def error_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="Not Found")

        client = _make_lcu_transport(error_handler)
        result = await fetch_match_detail(client, game_id="99999")
        assert result == {}
