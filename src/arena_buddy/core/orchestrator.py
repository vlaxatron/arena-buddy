"""Game polling orchestrator for Arena Buddy.

Polls the League Live Client Data API every 2 seconds, detects game state
transitions (start/end), and emits events for the UI and match capture.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from arena_buddy.core.game_state import GameState, poll_game_state

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class GameEventType(Enum):
    """Types of events emitted by the orchestrator."""

    GAME_START = auto()
    GAME_END = auto()
    CHAMPION_DETECTED = auto()
    STATUS = auto()
    IDLE = auto()
    ERROR = auto()


@dataclass
class GameEvent:
    """An event emitted by the GameOrchestrator during its poll loop.

    Attributes:
        type: The :class:`GameEventType` of this event.
        champion: The detected champion name (if any).
        game_mode: The game mode (e.g. ``"CHERRY"``, ``"CLASSIC"``).
        game_id: The game ID from the Live Client API.
        message: A human-readable message (for status/error events).
    """

    type: GameEventType
    champion: str | None = None
    game_mode: str | None = None
    game_id: str | None = None
    message: str | None = None

    @property
    def is_arena(self) -> bool:
        """Return True if this event is from an Arena game."""
        return self.game_mode == "CHERRY" if self.game_mode else False

    @property
    def full_details(self) -> dict[str, Any]:
        """Return a dict with all non-None fields for serialization."""
        return {
            k: v
            for k, v in {
                "type": self.type.name,
                "champion": self.champion,
                "game_mode": self.game_mode,
                "game_id": self.game_id,
                "message": self.message,
            }.items()
            if v is not None
        }


# ---------------------------------------------------------------------------
# Callback type
# ---------------------------------------------------------------------------

EventCallback = Callable[[GameEvent], Awaitable[None]]

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class GameOrchestrator:
    """Polls the Live Client Data API and emits game state transition events.

    Runs in a background asyncio task.  Callbacks registered via
    :meth:`on_event` receive every event emitted by the poll loop.

    Args:
        db_path: Path to the Arena Buddy SQLite database (used for
            match storage after game-end detection).
        liveclient_url: Base URL for the Live Client Data API.
            Default: ``"https://127.0.0.1:2999/liveclientdata"``.
        poll_interval: Seconds between polls. Default: 2.0.
    """

    def __init__(
        self,
        db_path: str | Path,
        liveclient_url: str = "https://127.0.0.1:2999/liveclientdata",
        poll_interval: float = 2.0,
    ) -> None:
        self._db_path = str(db_path)
        self._liveclient_url = liveclient_url
        self._poll_interval = poll_interval
        self._callbacks: list[tuple[EventCallback, int]] = []
        self._callback_counter: int = 0
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._previous_state: GameState = GameState()
        self._current_state: GameState = GameState()
        self._last_game_id: str | None = None
        self._last_game_mode: str | None = None
        self._client: httpx.AsyncClient | None = None

    # -- Properties -------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return True if the poll loop is active."""
        return self._running

    @property
    def current_state(self) -> GameState:
        """Return the most recently polled :class:`GameState`."""
        return self._current_state

    @property
    def last_game_id(self) -> str | None:
        """Return the game_id of the most recently ended game."""
        return self._last_game_id

    @property
    def last_game_mode(self) -> str | None:
        """Return the game_mode of the most recently ended game."""
        return self._last_game_mode

    # -- Callback management ----------------------------------------------

    def on_event(self, callback: EventCallback) -> Callable[[], None]:
        """Register an async callback to receive :class:`GameEvent` instances.

        Returns:
            An unsubscribe function.  Call it to stop receiving events.
        """
        idx = self._callback_counter
        self._callback_counter += 1
        self._callbacks.append((callback, idx))

        def unsubscribe() -> None:
            self._callbacks = [(cb, i) for cb, i in self._callbacks if i != idx]

        return unsubscribe

    # -- Poll loop --------------------------------------------------------

    async def start(self) -> None:
        """Start the background poll loop.

        Creates an :class:`httpx.AsyncClient` and begins polling.
        Safe to call multiple times — a second call is a no-op while
        the loop is already running.
        """
        if self._running:
            return

        self._client = httpx.AsyncClient(verify=False)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("GameOrchestrator poll loop started (interval=%ss)", self._poll_interval)

    async def stop(self) -> None:
        """Stop the background poll loop and clean up resources."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("GameOrchestrator stopped")

    async def _poll_loop(self) -> None:
        """Background task: poll game state and emit events on transitions."""
        while self._running:
            try:
                if self._client is None:
                    self._client = httpx.AsyncClient(verify=False)

                new_state = await poll_game_state(self._client, self._liveclient_url)
                self._current_state = new_state

                events = self._check_transition(self._previous_state, new_state)
                self._previous_state = new_state

                for event in events:
                    try:
                        await self._emit(event)
                    except Exception:
                        logger.exception("Emit error for event %s", event.type)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Poll loop error: %s", exc)
                try:
                    await self._emit(
                        GameEvent(
                            type=GameEventType.ERROR,
                            message="League client not detected — is it running?",
                        )
                    )
                except Exception:
                    pass

            await asyncio.sleep(self._poll_interval)

    # -- Transition detection ---------------------------------------------

    def _check_transition(
        self, prev: GameState, curr: GameState
    ) -> list[GameEvent]:
        """Check for game state transitions and return events to emit.

        Args:
            prev: The previous :class:`GameState`.
            curr: The current :class:`GameState`.

        Returns:
            A list of :class:`GameEvent` instances to emit (may be empty).
        """
        events: list[GameEvent] = []

        # Game start: went from idle/champ_select to in_game
        if (
            curr.status == "in_game"
            and prev.status in ("none", "champ_select")
            and prev.status != curr.status
        ):
            if self._is_arena_game(curr):
                events.append(
                    GameEvent(
                        type=GameEventType.GAME_START,
                        champion=curr.champion,
                        game_mode=curr.game_mode,
                        game_id=curr.game_id,
                    )
                )
                logger.info(
                    "Arena game started — champion=%s mode=%s",
                    curr.champion,
                    curr.game_mode,
                )

        # Game end: went from in_game to none
        if prev.status == "in_game" and curr.status != "in_game":
            if self._is_arena_game(prev):
                self._last_game_id = prev.game_id
                self._last_game_mode = prev.game_mode
                events.append(
                    GameEvent(
                        type=GameEventType.GAME_END,
                        champion=prev.champion,
                        game_mode=prev.game_mode,
                        game_id=prev.game_id,
                    )
                )
                logger.info(
                    "Arena game ended — champion=%s game_id=%s",
                    prev.champion,
                    prev.game_id,
                )

        return events

    @staticmethod
    def _is_arena_game(state: GameState) -> bool:
        """Return True if *state* represents an Arena (CHERRY) game."""
        return state.game_mode == "CHERRY"

    # -- Event emission ---------------------------------------------------

    async def emit(self, event: GameEvent) -> None:
        """Deliver *event* to all registered callbacks (public).

        This is the public, awaitable version.  Use this directly in
        tests and external callers.  Callback exceptions are logged
        but do not prevent other callbacks from receiving the event.
        """
        await self._emit(event)

    async def _emit(self, event: GameEvent) -> None:
        """Deliver *event* to all registered callbacks.

        Callback exceptions are logged but do not prevent other callbacks
        from receiving the event.
        """
        for cb, _ in self._callbacks:
            try:
                await cb(event)
            except Exception:
                logger.exception("Callback error for event %s", event.type)
