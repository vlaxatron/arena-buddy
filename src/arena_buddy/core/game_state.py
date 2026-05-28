"""Game state poller for the League Live Client Data API.

Polls ``https://127.0.0.1:2999/liveclientdata/`` during active games to detect
game state transitions (start / end) and extract champion + game mode info.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class GameState:
    """Current state of the live game as reported by the Live Client Data API.

    Attributes:
        champion: The active player's champion name (e.g. "Lucian"), or None.
        game_mode: The current game mode (e.g. "CHERRY", "CLASSIC"), or None.
        game_id: The current game's ID if available, or None.
        status: One of "in_game", "champ_select", "ended", "none".
    """

    champion: Optional[str] = None
    game_mode: Optional[str] = None
    game_id: Optional[str] = None
    status: str = "none"


async def poll_game_state(
    client: httpx.AsyncClient, liveclient_url: str
) -> GameState:
    """Poll the Live Client Data API for the current game state.

    Makes HTTP GET requests to the Game Client API.  Handles connection
    errors / timeouts / bad responses as ``GameState(status="none")``.

    Args:
        client: An :class:`httpx.AsyncClient` (may use a mock transport in tests).
        liveclient_url: Base URL, e.g. ``"https://127.0.0.1:2999/liveclientdata"``.

    Returns:
        A :class:`GameState` reflecting the current state of the game.
    """
    base = liveclient_url.rstrip("/")

    try:
        # Try /allgamedata first — fast path that gives gameMode
        resp = await client.get(f"{base}/allgamedata", timeout=2.0)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        # Connection refused / timeout / bad JSON → no game
        return GameState()

    try:
        game_mode = data.get("gameData", {}).get("gameMode", None)
        active = data.get("activePlayer", {})
        champion = active.get("championName", None) or None
        game_id = data.get("gameData", {}).get("gameId", None)
    except (TypeError, AttributeError):
        return GameState()

    if game_mode and champion:
        return GameState(
            champion=champion,
            game_mode=game_mode,
            game_id=str(game_id) if game_id else None,
            status="in_game",
        )
    elif champion:
        # Have champion but no game mode — likely champ select or early load
        return GameState(champion=champion, status="in_game")
    else:
        # Connected but no champion / mode — unusual; treat as none
        return GameState()


def detect_game_start(prev: GameState, curr: GameState) -> bool:
    """Detect whether a game just started based on state transitions.

    A game start is detected when the status transitions from ``"none"``
    or ``"champ_select"`` to ``"in_game"`` with a game mode present.

    Args:
        prev: The previous :class:`GameState`.
        curr: The current :class:`GameState`.

    Returns:
        ``True`` if a new game has started.
    """
    if curr.status != "in_game":
        return False
    if prev.status == curr.status:
        return False
    return prev.status in ("none", "champ_select")


def detect_game_end(prev: GameState, curr: GameState) -> bool:
    """Detect whether a game just ended based on state transitions.

    A game end is detected when the status transitions from ``"in_game"``
    or ``"champ_select"`` to ``"ended"``.

    Args:
        prev: The previous :class:`GameState`.
        curr: The current :class:`GameState`.

    Returns:
        ``True`` if the game has ended.
    """
    if curr.status != "ended":
        return False
    if prev.status == curr.status:
        return False
    return prev.status in ("in_game", "champ_select")
