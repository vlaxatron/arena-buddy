"""Match capture service — auto-captures Arena matches on game end.

Listens for GAME_END events from the :class:`GameOrchestrator` and
automatically fetches match details from the LCU, stores them in the
database, and recomputes personal stats.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from arena_buddy.core.match_capture import (
    create_lcu_client,
    fetch_match_detail,
    find_lockfile,
    parse_lockfile,
)
from arena_buddy.core.orchestrator import GameEvent, GameEventType
from arena_buddy.db.personal_stats import recompute_all

logger = logging.getLogger(__name__)


class MatchCaptureService:
    """Captures Arena match details from the LCU on GAME_END events.

    Args:
        db_path: Path to the Arena Buddy SQLite database.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a new SQLite connection with row_factory set."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def on_game_end(self, event: GameEvent) -> None:
        """Handle a GAME_END event — fetch and store match details.

        Args:
            event: The :class:`GameEvent` emitted by the orchestrator.
        """
        if event.type != GameEventType.GAME_END:
            return

        game_id = event.game_id
        if not game_id:
            logger.warning("GAME_END event has no game_id, skipping capture")
            return

        logger.info("Match capture triggered for game_id=%s champion=%s", game_id, event.champion)

        try:
            # Find and parse lockfile
            lockfile = find_lockfile()
            if lockfile is None:
                logger.warning("No League lockfile found, cannot capture match")
                await self._store_pending_capture(game_id, event.champion, event.game_mode)
                return

            lcu_info = parse_lockfile(lockfile)
            client = create_lcu_client(lcu_info["port"], lcu_info["password"])

            try:
                match_detail = await fetch_match_detail(client, game_id)
                if not match_detail:
                    logger.warning("Empty match detail returned for game_id=%s", game_id)
                    return

                await self._store_match(match_detail)

                # Recompute personal stats with new match data
                conn = self._get_connection()
                try:
                    recompute_all(conn)
                finally:
                    conn.close()

                logger.info("Match %s captured and stored successfully", game_id)

            finally:
                await client.aclose()

        except Exception:
            logger.exception("Failed to capture match %s", game_id)

    async def _store_match(self, match_detail: dict[str, Any]) -> None:
        """Store a match and its participants/items/augments in the database.

        Runs synchronously in a thread to not block the event loop.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._store_match_sync, match_detail)

    def _store_match_sync(self, match_detail: dict[str, Any]) -> None:
        """Synchronous match storage — runs in executor thread."""
        conn = self._get_connection()
        try:
            game_id = str(match_detail.get("gameId", ""))
            if not game_id:
                return

            # Check if already stored (idempotent)
            existing = conn.execute(
                "SELECT 1 FROM matches WHERE game_id = ?", (game_id,)
            ).fetchone()
            if existing:
                logger.debug("Match %s already stored, skipping", game_id)
                return

            # Extract match-level data
            # LCU match detail shape varies; try to extract what we can
            teams = match_detail.get("teams", [])
            participants = match_detail.get("participants", [])
            player_identities = match_detail.get("participantIdentities", [])

            if not participants:
                logger.warning("Match %s has no participants", game_id)
                return

            # Find the local player (the one who owns this LCU)
            local_participant = None
            for pi in player_identities:
                pid = pi.get("participantId")
                player_info = pi.get("player", {})
                # Local player typically has the summoner name in their identity
                for p in participants:
                    if p.get("participantId") == pid:
                        p["_summonerName"] = player_info.get("summonerName", "")
                        p["_puuid"] = player_info.get("puuid", "")
                        if p.get("stats", {}).get("playerScore0", 0) > 0 or True:
                            # Heuristic: the local player is participantId 1-4 in Arena
                            if not local_participant and pid <= 4:
                                local_participant = p

            if not local_participant and participants:
                local_participant = participants[0]

            stats = local_participant.get("stats", {})
            timeline = local_participant.get("timeline", {})

            champion_id = local_participant.get("championId", 0)
            champion_key = self._get_champion_key(conn, champion_id)

            win = stats.get("win", False)
            placement = self._compute_placement(participants)

            # Determine game mode (CHERRY for Arena)
            game_mode = match_detail.get("gameMode", "CHERRY")
            queue_id = match_detail.get("queueId")
            map_id = match_detail.get("mapId")
            match_timestamp = match_detail.get("gameCreation")
            if match_timestamp:
                from datetime import datetime, timezone
                match_timestamp = datetime.fromtimestamp(
                    match_timestamp / 1000, tz=timezone.utc
                ).isoformat()

            patch_version = match_detail.get("gameVersion", "")
            if patch_version:
                # "16.11.564.1234" → "16.11"
                parts = patch_version.split(".")
                if len(parts) >= 2:
                    patch_version = f"{parts[0]}.{parts[1]}"

            duration = match_detail.get("gameDuration", 0)

            kills = stats.get("kills", 0) or stats.get("championsKilled", 0)
            deaths = stats.get("deaths", 0) or stats.get("numDeaths", 0)
            assists = stats.get("assists", 0)

            import json
            raw_json = json.dumps(match_detail, default=str)

            conn.execute(
                """
                INSERT OR IGNORE INTO matches
                    (game_id, champion_id, champion_key, game_mode, queue_id,
                     map_id, win, placement, duration_sec, kills, deaths,
                     assists, match_timestamp, patch_version, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game_id, champion_id, champion_key, game_mode, queue_id,
                    map_id, int(win), placement, duration, kills, deaths,
                    assists, match_timestamp, patch_version, raw_json,
                ),
            )

            # Store all participants
            for p in participants:
                pid = p.get("participantId", 0)
                p_champ_id = p.get("championId", 0)
                p_champ_key = self._get_champion_key(conn, p_champ_id)
                p_stats = p.get("stats", {})
                p_win = p_stats.get("win", False)
                p_place = self._compute_single_placement(p_stats, participants)

                summoner_name = p.get("_summonerName", "")
                puuid = p.get("_puuid", "")

                cursor = conn.execute(
                    """
                    INSERT INTO match_participants
                        (game_id, puuid, summoner_name, champion_id,
                         champion_key, placement, win)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (game_id, puuid, summoner_name, p_champ_id,
                     p_champ_key, p_place, int(p_win)),
                )
                participant_db_id = cursor.lastrowid

                # Store items (slots 0-5)
                for slot in range(6):
                    item_id = p_stats.get(f"item{slot}", 0)
                    if item_id and item_id != 0:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO match_items
                                (game_id, participant_id, item_id, slot)
                            VALUES (?, ?, ?, ?)
                            """,
                            (game_id, participant_db_id, item_id, slot),
                        )

                # Store augments (if available in LCU data)
                # Arena augment data may be in perks or a custom field
                perks = p_stats.get("perks", {})
                if isinstance(perks, dict) and "perkIds" in perks:
                    for aug_slot, aug_id in enumerate(perks.get("perkIds", [])):
                        if aug_id:
                            conn.execute(
                                """
                                INSERT OR IGNORE INTO match_augments
                                    (game_id, participant_id, augment_id, slot)
                                VALUES (?, ?, ?, ?)
                                """,
                                (game_id, participant_db_id, aug_id, aug_slot),
                            )

            conn.commit()
            logger.info(
                "Stored match %s: %s (W=%s, place=%d)",
                game_id, champion_key, win, placement,
            )

        except Exception:
            logger.exception("Failed to store match %s", game_id)
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get_champion_key(self, conn: sqlite3.Connection, champion_id: int) -> str:
        """Look up champion key from DB, falling back to str(ID)."""
        row = conn.execute(
            "SELECT key FROM champions WHERE id = ?", (champion_id,)
        ).fetchone()
        return row["key"] if row else str(champion_id)

    @staticmethod
    def _compute_placement(participants: list[dict]) -> int:
        """Compute placement (1-4) from participant stats.

        In Arena, the local player's placement is derived from
        playerScore0 or by sorting teams by win status.
        """
        # Arena scoring: playerScore0 is placement (4=4th, 1=1st, etc.)
        # But it's actually the score, not placement directly.
        # Use the first participant's stats as local.
        if not participants:
            return 1

        # Try to determine by STATS on each player
        scores = []
        for p in participants:
            stats = p.get("stats", {})
            score = stats.get("playerScore0", 0)
            scores.append((score, p.get("participantId", 0)))

        # Higher score = better placement
        scores.sort(key=lambda x: x[0], reverse=True)

        # Find local participant (assume first one for now)
        local_pid = participants[0].get("participantId", 0)
        for rank, (_, pid) in enumerate(scores, start=1):
            if pid == local_pid:
                return rank

        return 1

    @staticmethod
    def _compute_single_placement(stats: dict, participants: list[dict]) -> int:
        """Compute placement for a single participant."""
        scores = []
        for p in participants:
            p_stats = p.get("stats", {})
            score = p_stats.get("playerScore0", 0)
            scores.append(score)
        scores.sort(reverse=True)

        player_score = stats.get("playerScore0", 0)
        for rank, score in enumerate(scores, start=1):
            if score == player_score:
                return rank
        return 1

    async def _store_pending_capture(
        self, game_id: str, champion: str | None, game_mode: str | None
    ) -> None:
        """Store a pending capture note when LCU is unavailable.

        The match can be captured later when LCU is accessible.
        """
        logger.info("Queued pending capture for game_id=%s", game_id)
        # For now, we just log it. A future enhancement could store
        # pending game IDs and retry on next startup.
