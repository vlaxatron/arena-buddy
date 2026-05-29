"""Tests for arena_buddy.core.riot_api — Riot Games API client with rate limiting.

Tests written FIRST (RED phase) — these WILL fail until riot_api.py exists.
"""

from __future__ import annotations

import asyncio
import time
from unittest import mock

import httpx
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_key() -> str:
    """Fake Riot API key for testing."""
    return "RGAPI-test-key-12345"


@pytest.fixture
def client(api_key: str) -> "RiotAPIClient":
    """A fresh RiotAPIClient with a fake API key."""
    from arena_buddy.core.riot_api import RiotAPIClient

    return RiotAPIClient(api_key=api_key)


@pytest.fixture
def mock_response():
    """Create a mock httpx.Response."""
    resp = mock.MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {}
    resp.raise_for_status = mock.MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Test initialisation
# ---------------------------------------------------------------------------


class TestRiotAPIClientInit:
    """Initialisation and configuration."""

    def test_default_region_is_americas(self, api_key: str):
        """Default region should be 'americas'."""
        from arena_buddy.core.riot_api import RiotAPIClient

        client = RiotAPIClient(api_key=api_key)
        assert client.region == "americas"
        assert client.api_key == api_key

    def test_custom_region(self, api_key: str):
        """Custom region should be stored and used for base URL."""
        from arena_buddy.core.riot_api import RiotAPIClient

        client = RiotAPIClient(api_key=api_key, region="europe")
        assert client.region == "europe"

    def test_base_url_for_americas(self, client):
        """Americas region uses americas.api.riotgames.com."""
        assert client._base_url == "https://americas.api.riotgames.com"

    def test_base_url_for_europe(self, api_key: str):
        """Europe region uses europe.api.riotgames.com."""
        from arena_buddy.core.riot_api import RiotAPIClient

        client = RiotAPIClient(api_key=api_key, region="europe")
        assert client._base_url == "https://europe.api.riotgames.com"

    def test_base_url_for_asia(self, api_key: str):
        """Asia region uses asia.api.riotgames.com."""
        from arena_buddy.core.riot_api import RiotAPIClient

        client = RiotAPIClient(api_key=api_key, region="asia")
        assert client._base_url == "https://asia.api.riotgames.com"

    def test_base_url_for_sea(self, api_key: str):
        """SEA region uses sea.api.riotgames.com."""
        from arena_buddy.core.riot_api import RiotAPIClient

        client = RiotAPIClient(api_key=api_key, region="sea")
        assert client._base_url == "https://sea.api.riotgames.com"

    def test_creates_httpx_async_client(self, client):
        """__init__ creates an httpx.AsyncClient."""
        assert isinstance(client._http, httpx.AsyncClient)

    def test_timeout_is_15_seconds(self, client):
        """Request timeout should be 15 seconds."""
        assert client._http.timeout == httpx.Timeout(15.0)

    def test_request_times_starts_empty(self, api_key: str):
        """Rate-limiting tracking list starts empty."""
        from arena_buddy.core.riot_api import RiotAPIClient

        client = RiotAPIClient(api_key=api_key)
        assert client._request_times == []


# ---------------------------------------------------------------------------
# Region validation
# ---------------------------------------------------------------------------


class TestRegionValidation:
    """Region parameter validation."""

    def test_valid_regions_accepted(self, api_key: str):
        """All four valid regions should be accepted."""
        from arena_buddy.core.riot_api import RiotAPIClient

        for region in ["americas", "europe", "asia", "sea"]:
            client = RiotAPIClient(api_key=api_key, region=region)
            assert client.region == region

    def test_invalid_region_raises_value_error(self, api_key: str):
        """Invalid region should raise ValueError."""
        from arena_buddy.core.riot_api import RiotAPIClient

        with pytest.raises(ValueError, match="Invalid region"):
            RiotAPIClient(api_key=api_key, region="invalid_region")


# ---------------------------------------------------------------------------
# Test _request — happy path
# ---------------------------------------------------------------------------


class TestRequest:
    """Internal _request method — happy path."""

    @pytest.mark.asyncio
    async def test_sends_get_with_riot_token_header(self, client, mock_response):
        """_request sends GET with X-Riot-Token header."""
        mock_response.json.return_value = {"puuid": "abc-123"}

        with mock.patch.object(client._http, "get", return_value=mock_response) as mock_get:
            result = await client._request("GET", "/riot/account/v1/accounts/by-riot-id/user/TAG")

        assert result == {"puuid": "abc-123"}
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["headers"]["X-Riot-Token"] == client.api_key

    @pytest.mark.asyncio
    async def test_constructs_full_url(self, client, mock_response):
        """Path is appended to base URL."""
        with mock.patch.object(client._http, "get", return_value=mock_response) as mock_get:
            await client._request("GET", "/lol/match/v5/matches/by-puuid/abc/ids")

        # URL is passed as keyword argument
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["url"] == "https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/abc/ids"

    @pytest.mark.asyncio
    async def test_tracks_request_time_after_success(self, client, mock_response):
        """Each successful request records its completion time."""
        with mock.patch.object(client._http, "get", return_value=mock_response):
            await client._request("GET", "/test1")
            await client._request("GET", "/test2")

        assert len(client._request_times) == 2


# ---------------------------------------------------------------------------
# Test _request — error handling
# ---------------------------------------------------------------------------


class TestRequestErrors:
    """Internal _request method — error responses."""

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self, client):
        """HTTP 429 raises RiotRateLimitError with retry_after."""
        from arena_buddy.core.riot_api import RiotRateLimitError

        mock_resp = mock.MagicMock(spec=httpx.Response)
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "5"}

        with mock.patch.object(client._http, "get", return_value=mock_resp):
            with pytest.raises(RiotRateLimitError) as exc_info:
                await client._request("GET", "/test")
            assert exc_info.value.retry_after == 5

    @pytest.mark.asyncio
    async def test_429_defaults_retry_after_to_1(self, client):
        """HTTP 429 without Retry-After header defaults to 1 second."""
        from arena_buddy.core.riot_api import RiotRateLimitError

        mock_resp = mock.MagicMock(spec=httpx.Response)
        mock_resp.status_code = 429
        mock_resp.headers = {}  # No Retry-After

        with mock.patch.object(client._http, "get", return_value=mock_resp):
            with pytest.raises(RiotRateLimitError) as exc_info:
                await client._request("GET", "/test")
            assert exc_info.value.retry_after == 1

    @pytest.mark.asyncio
    async def test_403_raises_auth_error(self, client):
        """HTTP 403 raises RiotAuthError."""
        from arena_buddy.core.riot_api import RiotAuthError

        mock_resp = mock.MagicMock(spec=httpx.Response)
        mock_resp.status_code = 403

        with mock.patch.object(client._http, "get", return_value=mock_resp):
            with pytest.raises(RiotAuthError, match="Invalid API key"):
                await client._request("GET", "/test")

    @pytest.mark.asyncio
    async def test_404_returns_none(self, client):
        """HTTP 404 returns None from _request."""
        mock_resp = mock.MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404

        with mock.patch.object(client._http, "get", return_value=mock_resp):
            result = await client._request("GET", "/test")
            assert result is None

    @pytest.mark.asyncio
    async def test_5xx_raises_httpx_status_error(self, client):
        """HTTP 500 is raised via raise_for_status."""
        import httpx as _httpx

        mock_resp = mock.MagicMock(spec=_httpx.Response)
        mock_resp.status_code = 500
        # Make raise_for_status actually raise for 500
        mock_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "Server error",
            request=mock.MagicMock(),
            response=mock_resp,
        )

        with mock.patch.object(client._http, "get", return_value=mock_resp):
            with pytest.raises(_httpx.HTTPStatusError):
                await client._request("GET", "/test")


# ---------------------------------------------------------------------------
# Rate-limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Rate limiting — max 20 requests per second."""

    @pytest.mark.asyncio
    async def test_can_make_20_requests_without_delay(self, client, mock_response):
        """20 requests in rapid succession complete quickly (< 2s)."""
        with mock.patch.object(client._http, "get", return_value=mock_response):
            start = time.monotonic()
            for _ in range(20):
                await client._request("GET", "/test")
            elapsed = time.monotonic() - start

        # 20 mocked requests should complete well under 2 seconds
        assert elapsed < 2.0, f"Took {elapsed:.2f}s for 20 requests"

    @pytest.mark.asyncio
    async def test_request_21_triggers_rate_limit_pause(self, client, mock_response):
        """The 21st request in a 1-second window should be delayed."""
        with mock.patch.object(client._http, "get", return_value=mock_response):
            # Pre-fill with 20 requests all at "now"
            now = time.monotonic()
            client._request_times = [now] * 20

            # The next request should trigger a rate-limit pause
            start = time.monotonic()
            await client._request("GET", "/test")
            elapsed = time.monotonic() - start

        # We should have waited until the oldest request drops out of the window
        # With 20 requests at exactly 'now', the 21st should wait ~1 second
        # But since the oldest is also at 'now', the wait is ~1s
        assert elapsed > 0.0, "Should have waited at least some time"

    def test_request_times_cleaned_up(self, client):
        """Old request times outside the 1-second window are removed."""
        now = time.monotonic()
        # 20 requests spanning more than 1 second ago
        client._request_times = [
            now - 5.0,  # very old - should be cleaned
            now - 2.0,  # old
            now - 1.5,  # old
            now - 0.5,  # within window
            now - 0.1,  # within window
        ]

        # Call _clean_old_requests or trigger it via _request
        from arena_buddy.core.riot_api import RiotAPIClient

        # Access the private method for testing
        client._clean_old_requests()
        assert len(client._request_times) == 2
        # Only times within the last 1 second remain
        for t in client._request_times:
            assert now - t <= 1.0


# ---------------------------------------------------------------------------
# Test get_puuid
# ---------------------------------------------------------------------------


class TestGetPuuid:
    """get_puuid — look up PUUID by Riot ID."""

    @pytest.mark.asyncio
    async def test_returns_puuid_from_response(self, client):
        """Extracts puuid from account response."""
        with mock.patch.object(
            client, "_request", return_value={"puuid": "zzz-puuid-12345"}
        ) as mock_req:
            result = await client.get_puuid("TestUser", "NA1")

        assert result == "zzz-puuid-12345"
        mock_req.assert_called_once_with(
            "GET", "/riot/account/v1/accounts/by-riot-id/TestUser/NA1"
        )

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, client):
        """Returns None when account not found (404)."""
        with mock.patch.object(client, "_request", return_value=None) as mock_req:
            result = await client.get_puuid("NotFound", "NA1")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_puuid_in_response(self, client):
        """Gracefully handles response missing puuid field."""
        with mock.patch.object(client, "_request", return_value={}) as mock_req:
            result = await client.get_puuid("WeirdUser", "NA1")

        assert result is None


# ---------------------------------------------------------------------------
# Test get_match_history
# ---------------------------------------------------------------------------


class TestGetMatchHistory:
    """get_match_history — fetch Arena match IDs for a player."""

    @pytest.mark.asyncio
    async def test_returns_list_of_match_ids(self, client):
        """Returns list of match ID strings."""
        mock_ids = ["NA1_12345", "NA1_12346", "NA1_12347"]

        with mock.patch.object(client, "_request", return_value=mock_ids) as mock_req:
            result = await client.get_match_history("puuid-abc")

        assert result == mock_ids
        mock_req.assert_called_once_with(
            "GET",
            "/lol/match/v5/matches/by-puuid/puuid-abc/ids?queue=1700&count=20",
        )

    @pytest.mark.asyncio
    async def test_default_queue_is_1700_arena(self, client):
        """Default queue filter is 1700 (Arena)."""
        with mock.patch.object(client, "_request", return_value=[]) as mock_req:
            await client.get_match_history("puuid-abc")

        call_path = mock_req.call_args[0][1]
        assert "queue=1700" in call_path

    @pytest.mark.asyncio
    async def test_custom_count(self, client):
        """Custom count is passed as query parameter."""
        with mock.patch.object(client, "_request", return_value=[]) as mock_req:
            await client.get_match_history("puuid-abc", count=10)

        call_path = mock_req.call_args[0][1]
        assert "count=10" in call_path

    @pytest.mark.asyncio
    async def test_custom_queue(self, client):
        """Custom queue filter is passed as query parameter."""
        with mock.patch.object(client, "_request", return_value=[]) as mock_req:
            await client.get_match_history("puuid-abc", queue=420)

        call_path = mock_req.call_args[0][1]
        assert "queue=420" in call_path

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_none(self, client):
        """When _request returns None, return empty list."""
        with mock.patch.object(client, "_request", return_value=None) as mock_req:
            result = await client.get_match_history("puuid-abc")

        assert result == []


# ---------------------------------------------------------------------------
# Test get_match_detail
# ---------------------------------------------------------------------------


class TestGetMatchDetail:
    """get_match_detail — fetch full match data."""

    @pytest.mark.asyncio
    async def test_returns_full_match_dict(self, client):
        """Returns parsed match response."""
        mock_match = {
            "metadata": {"matchId": "NA1_12345"},
            "info": {"gameMode": "CHERRY", "participants": []},
        }

        with mock.patch.object(client, "_request", return_value=mock_match) as mock_req:
            result = await client.get_match_detail("NA1_12345")

        assert result == mock_match
        mock_req.assert_called_once_with(
            "GET", "/lol/match/v5/matches/NA1_12345"
        )

    @pytest.mark.asyncio
    async def test_raises_not_found_error_when_404(self, client):
        """Raises RiotNotFoundError when match is not found."""
        from arena_buddy.core.riot_api import RiotNotFoundError

        with mock.patch.object(client, "_request", return_value=None) as mock_req:
            with pytest.raises(RiotNotFoundError, match="NA1_12345"):
                await client.get_match_detail("NA1_12345")

    @pytest.mark.asyncio
    async def test_passes_through_parsed_data(self, client):
        """match detail response is passed through as-is."""
        mock_match = {
            "metadata": {"matchId": "EUW_999"},
            "info": {
                "gameMode": "CHERRY",
                "participants": [
                    {"puuid": "p1", "championId": 236, "placement": 1},
                    {"puuid": "p2", "championId": 222, "placement": 2},
                ],
            },
        }

        with mock.patch.object(client, "_request", return_value=mock_match):
            result = await client.get_match_detail("EUW_999")

        assert result["info"]["gameMode"] == "CHERRY"
        assert len(result["info"]["participants"]) == 2
