"""Riot Games API client with rate limiting.

Provides ``RiotAPIClient`` — an async HTTP client for the Riot Games
API (Account v1 and Match v5 endpoints).  Enforces Riot's 20 req/s rate
limit and handles common error responses (401, 403, 404, 429).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Region → base URL mapping
# ---------------------------------------------------------------------------

_REGION_BASE_URLS: dict[str, str] = {
    "americas": "https://americas.api.riotgames.com",
    "europe": "https://europe.api.riotgames.com",
    "asia": "https://asia.api.riotgames.com",
    "sea": "https://sea.api.riotgames.com",
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RiotRateLimitError(Exception):
    """Raised when the Riot API returns HTTP 429 (rate limited)."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited — retry after {retry_after}s")


class RiotAuthError(Exception):
    """Raised when the Riot API returns HTTP 403 (invalid API key)."""

    def __init__(self, message: str = "Invalid API key") -> None:
        super().__init__(message)


class RiotNotFoundError(Exception):
    """Raised when the Riot API returns HTTP 404 for a match."""

    def __init__(self, match_id: str) -> None:
        self.match_id = match_id
        super().__init__(f"Match '{match_id}' not found")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class RiotAPIClient:
    """Async HTTP client for the Riot Games API.

    Enforces Riot's rate limit of **20 requests per second** by tracking
    request timestamps and sleeping when the window is full.

    Parameters:
        api_key: Riot Games API key (from env var or settings).
        region: Routing region — one of ``americas``, ``europe``,
                ``asia``, ``sea``.
    """

    _MAX_REQUESTS_PER_SECOND: int = 20
    _WINDOW_SECONDS: float = 1.0

    def __init__(self, api_key: str, region: str = "americas") -> None:
        if region not in _REGION_BASE_URLS:
            raise ValueError(
                f"Invalid region: {region!r}. "
                f"Must be one of {list(_REGION_BASE_URLS)}"
            )

        self.api_key = api_key
        self.region = region
        self._base_url = _REGION_BASE_URLS[region]

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
        )

        # Rate-limit tracking: deque of monotonic timestamps
        self._request_times: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_puuid(self, game_name: str, tag_line: str) -> str | None:
        """Resolve a Riot ID (gameName + tagLine) to a PUUID.

        Returns:
            PUUID string, or ``None`` if the account is not found.
        """
        path = f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        data = await self._request("GET", path)
        if data is None:
            return None
        return data.get("puuid")

    async def get_match_history(
        self, puuid: str, queue: int = 1700, count: int = 20
    ) -> list[str]:
        """Fetch Arena match IDs for a player.

        Parameters:
            puuid: Player's PUUID.
            queue: Queue ID (1700 = Arena).
            count: Maximum number of match IDs to return.

        Returns:
            List of match ID strings (empty list on failure).
        """
        path = (
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
            f"?queue={queue}&count={count}"
        )
        data = await self._request("GET", path)
        if data is None:
            return []
        return data  # type: ignore[return-value]

    async def get_match_detail(self, match_id: str) -> dict[str, Any]:
        """Fetch full match data for a single match.

        Returns:
            Parsed match response dict.

        Raises:
            RiotNotFoundError: If the match is not found (404).
        """
        path = f"/lol/match/v5/matches/{match_id}"
        data = await self._request("GET", path)
        if data is None:
            raise RiotNotFoundError(match_id)
        return data  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str) -> dict[str, Any] | None:
        """Execute a rate-limited HTTP request to the Riot API.

        Parameters:
            method: HTTP method (``GET``).
            path: API path (e.g., ``/riot/account/v1/...``).

        Returns:
            Parsed JSON response dict, or ``None`` on 404.

        Raises:
            RiotRateLimitError: On HTTP 429.
            RiotAuthError: On HTTP 403.
            httpx.HTTPStatusError: On other non-2xx responses.
        """
        url = f"{self._base_url}{path}"

        # --- Rate limit: enforce 20 req/s ---
        await self._enforce_rate_limit()

        try:
            response = await self._http.get(
                url=url,
                headers={"X-Riot-Token": self.api_key},
            )

            # Record request time *after* the response
            self._request_times.append(time.monotonic())

            # --- Handle status codes ---
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "1"))
                raise RiotRateLimitError(retry_after)

            if response.status_code == 403:
                raise RiotAuthError("Invalid API key")

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

        except (RiotRateLimitError, RiotAuthError):
            raise
        except httpx.HTTPStatusError:
            raise  # Let caller handle

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _enforce_rate_limit(self) -> None:
        """Sleep if we've hit the 20 req/s rate limit.

        Removes request timestamps older than ``_WINDOW_SECONDS``, then
        checks whether the remaining count is at or above the limit.
        If so, waits until the oldest request drops out of the window.
        """
        self._clean_old_requests()

        while len(self._request_times) >= self._MAX_REQUESTS_PER_SECOND:
            # Sleep until the oldest request ages out of the window
            oldest = self._request_times[0]
            wait_time = oldest + self._WINDOW_SECONDS - time.monotonic()
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._clean_old_requests()

    def _clean_old_requests(self) -> None:
        """Remove request timestamps older than the rate-limit window."""
        now = time.monotonic()
        cutoff = now - self._WINDOW_SECONDS
        self._request_times = [t for t in self._request_times if t > cutoff]
