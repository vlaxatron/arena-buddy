"""LCU match history capture for Arena Buddy.

Talks to the League Client Update (LCU) API running at
``https://127.0.0.1:{port}/`` with ``riot:{password}`` Basic auth parsed
from the League lockfile.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# Known lockfile locations (Windows + macOS + Wine/Lutris via league_detector)
# ---------------------------------------------------------------------------

_KNOWN_LOCKFILE_LOCATIONS = [
    # Windows default
    r"C:\Riot Games\League of Legends\lockfile",
    # macOS default
    "/Applications/League of Legends.app/Contents/LoL/lockfile",
]


def _discover_lockfile_locations() -> list[str]:
    """Build a list of candidate lockfile paths.

    Uses :func:`arena_buddy.core.league_detector.find_league_install`
    to detect League installations and adds their lockfile paths, then
    appends the hardcoded fallbacks.
    """
    candidates = list(_KNOWN_LOCKFILE_LOCATIONS)
    try:
        from arena_buddy.core.league_detector import find_league_install
        install_path = find_league_install()
        if install_path is not None:
            lockfile = install_path / "lockfile"
            candidates.insert(0, str(lockfile))
    except Exception:
        pass
    return candidates


# ---------------------------------------------------------------------------
# Lockfile helpers
# ---------------------------------------------------------------------------

def find_lockfile() -> Optional[Path]:
    """Search known locations and detected installs for the League lockfile.

    Uses :func:`_discover_lockfile_locations` which combines hardcoded
    paths with :func:`arena_buddy.core.league_detector.find_league_install`.

    Returns:
        :class:`Path` to the lockfile if found, else ``None``.
    """
    for location in _discover_lockfile_locations():
        path = Path(location)
        if path.exists():
            return path
    return None


def parse_lockfile(path: Path) -> dict[str, Any]:
    """Parse a League lockfile into its components.

    Format: ``LeagueClient:{pid}:{port}:{password}:{protocol}``

    Args:
        path: Path to the lockfile.

    Returns:
        Dict with keys ``"pid"``, ``"port"``, ``"password"``, ``"protocol"``.

    Raises:
        ValueError: If the lockfile has an invalid format.
    """
    content = path.read_text().strip()
    if not content:
        raise ValueError("Invalid lockfile format: empty file")

    parts = content.split(":")
    if len(parts) != 5 or parts[0] != "LeagueClient":
        raise ValueError("Invalid lockfile format")

    try:
        pid = int(parts[1])
        port = int(parts[2])
    except ValueError:
        raise ValueError("Invalid lockfile format")

    return {
        "pid": pid,
        "port": port,
        "password": parts[3],
        "protocol": parts[4],
    }


# ---------------------------------------------------------------------------
# LCU HTTP client
# ---------------------------------------------------------------------------

def create_lcu_client(port: int, password: str) -> httpx.AsyncClient:
    """Create an :class:`httpx.AsyncClient` pre-configured for the LCU API.

    Uses Basic auth (``riot:{password}``) and disables SSL verification
    (the LCU uses self-signed certificates).

    Args:
        port: The port from the lockfile.
        password: The password from the lockfile.

    Returns:
        A ready-to-use :class:`httpx.AsyncClient`.
    """
    token = base64.b64encode(f"riot:{password}".encode()).decode()
    return httpx.AsyncClient(
        base_url=f"https://127.0.0.1:{port}",
        headers={"Authorization": f"Basic {token}"},
        verify=False,
    )


# ---------------------------------------------------------------------------
# Match history API
# ---------------------------------------------------------------------------

async def fetch_match_history(
    client: httpx.AsyncClient, puuid: str
) -> list[dict[str, Any]]:
    """Fetch recent match history for a summoner.

    Calls ``GET /lol-match-history/v1/products/lol/{puuid}/matches``.

    Args:
        client: A pre-configured :class:`httpx.AsyncClient` (from :func:`create_lcu_client`).
        puuid: The summoner's PUUID.

    Returns:
        A list of match summary dicts.  Empty list on error or no matches.
    """
    try:
        resp = await client.get(
            f"/lol-match-history/v1/products/lol/{puuid}/matches",
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("games", {}).get("games", [])
    except (httpx.HTTPError, ValueError):
        return []


async def fetch_match_detail(
    client: httpx.AsyncClient, game_id: str
) -> dict[str, Any]:
    """Fetch full detail for a single match.

    Calls ``GET /lol-match-history/v1/games/{game_id}``.

    Args:
        client: A pre-configured :class:`httpx.AsyncClient`.
        game_id: The numeric match ID.

    Returns:
        A dict with full match detail.  Empty dict on error.
    """
    try:
        resp = await client.get(
            f"/lol-match-history/v1/games/{game_id}",
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError):
        return {}
