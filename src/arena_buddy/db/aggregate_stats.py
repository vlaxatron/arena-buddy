"""Aggregate stats computation from personal match history.

Computes per-champion aggregate stats (win rate, average placement,
KDA, top items, top augments) from the matches/match_participants/
match_items/match_augments tables.

Also provides :func:`sync_riot_matches` to fetch new Arena matches
from the Riot Games API and store them in the local database.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from arena_buddy.core.riot_api import RiotAPIClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# compute_champion_stats
# ---------------------------------------------------------------------------

def compute_champion_stats(conn: sqlite3.Connection, champion_id: int) -> dict[str, Any]:
    """Compute aggregate stats for a champion from personal match history.

    Joins across ``matches`` → ``match_participants`` →
    ``match_items`` / ``match_augments`` to compute win rate, average
    placement, KDA, placement distribution, and top-5 items/augments.

    Args:
        conn: An open :class:`sqlite3.Connection` with ``row_factory`` set.
        champion_id: Champion database ID.

    Returns:
        A dict with keys: ``total_games``, ``wins``, ``losses``,
        ``win_rate``, ``avg_placement``, ``placement_distribution``,
        ``avg_kills``, ``avg_deaths``, ``avg_assists``, ``avg_kda``,
        ``top_items``, ``top_augments``.
    """
    # --- Basic match aggregates ---
    agg_row = conn.execute(
        """
        SELECT
            COUNT(*)                                     AS total_games,
            SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END)    AS wins,
            SUM(CASE WHEN win = 0 THEN 1 ELSE 0 END)    AS losses,
            AVG(placement)                               AS avg_placement,
            AVG(kills)                                   AS avg_kills,
            AVG(deaths)                                  AS avg_deaths,
            AVG(assists)                                 AS avg_assists,
            SUM(kills)                                   AS total_kills,
            SUM(deaths)                                  AS total_deaths,
            SUM(assists)                                 AS total_assists
        FROM matches
        WHERE champion_id = ?
        """,
        (champion_id,),
    ).fetchone()

    if agg_row is None:
        return _empty_champion_stats()

    total_games: int = agg_row["total_games"] or 0
    wins: int = agg_row["wins"] or 0
    losses: int = agg_row["losses"] or 0
    total_kills: int = agg_row["total_kills"] or 0
    total_deaths: int = agg_row["total_deaths"] or 0
    total_assists: int = agg_row["total_assists"] or 0

    win_rate: float
    if total_games > 0:
        win_rate = wins / total_games
    else:
        win_rate = 0.0

    avg_placement: float
    if total_games > 0 and agg_row["avg_placement"] is not None:
        avg_placement = float(agg_row["avg_placement"])
    else:
        avg_placement = 0.0

    avg_kills: float
    if total_games > 0 and agg_row["avg_kills"] is not None:
        avg_kills = float(agg_row["avg_kills"])
    else:
        avg_kills = 0.0

    avg_deaths: float
    if total_games > 0 and agg_row["avg_deaths"] is not None:
        avg_deaths = float(agg_row["avg_deaths"])
    else:
        avg_deaths = 0.0

    avg_assists: float
    if total_games > 0 and agg_row["avg_assists"] is not None:
        avg_assists = float(agg_row["avg_assists"])
    else:
        avg_assists = 0.0

    avg_kda: float
    if total_deaths > 0 and total_games > 0:
        avg_kda = total_kills / total_deaths
    else:
        avg_kda = 0.0

    # --- Placement distribution ---
    placement_dist = _compute_placement_distribution(conn, champion_id)

    # --- Top items ---
    top_items = _compute_top_items(conn, champion_id)

    # --- Top augments ---
    top_augments = _compute_top_augments(conn, champion_id)

    return {
        "total_games": total_games,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_placement": avg_placement,
        "placement_distribution": placement_dist,
        "avg_kills": avg_kills,
        "avg_deaths": avg_deaths,
        "avg_assists": avg_assists,
        "avg_kda": avg_kda,
        "top_items": top_items,
        "top_augments": top_augments,
    }


def _empty_champion_stats() -> dict[str, Any]:
    """Return a stats dict with all zero/default values."""
    return {
        "total_games": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "avg_placement": 0.0,
        "placement_distribution": {1: 0, 2: 0, 3: 0, 4: 0},
        "avg_kills": 0.0,
        "avg_deaths": 0.0,
        "avg_assists": 0.0,
        "avg_kda": 0.0,
        "top_items": [],
        "top_augments": [],
    }


def _compute_placement_distribution(
    conn: sqlite3.Connection, champion_id: int
) -> dict[int, int]:
    """Count games per placement (1-4) for a champion."""
    dist = {1: 0, 2: 0, 3: 0, 4: 0}
    rows = conn.execute(
        """
        SELECT placement, COUNT(*) AS cnt
        FROM matches
        WHERE champion_id = ? AND placement IS NOT NULL
        GROUP BY placement
        """,
        (champion_id,),
    ).fetchall()
    for row in rows:
        placement = row["placement"]
        if placement in dist:
            dist[placement] = row["cnt"]
    return dist


def _compute_top_items(
    conn: sqlite3.Connection, champion_id: int, limit: int = 5
) -> list[dict[str, Any]]:
    """Return top-N most-used items for a champion (by game count)."""
    rows = conn.execute(
        """
        SELECT
            i.id        AS item_id,
            i.name      AS item_name,
            i.icon_filename,
            COUNT(DISTINCT mp.game_id)                      AS games,
            SUM(CASE WHEN mp.win THEN 1 ELSE 0 END)        AS wins,
            CAST(SUM(CASE WHEN mp.win THEN 1 ELSE 0 END) AS REAL)
                / COUNT(DISTINCT mp.game_id)                AS win_rate
        FROM matches m
        JOIN match_participants mp
            ON mp.game_id = m.game_id AND mp.champion_id = m.champion_id
        JOIN match_items mi ON mi.participant_id = mp.id
        JOIN items i ON mi.item_id = i.id
        WHERE m.champion_id = ?
        GROUP BY i.id, i.name
        ORDER BY games DESC, win_rate DESC
        LIMIT ?
        """,
        (champion_id, limit),
    ).fetchall()

    return [
        {
            "item_id": row["item_id"],
            "item_name": row["item_name"],
            "games": row["games"],
            "wins": row["wins"],
            "win_rate": row["win_rate"],
        }
        for row in rows
    ]


def _compute_top_augments(
    conn: sqlite3.Connection, champion_id: int, limit: int = 5
) -> list[dict[str, Any]]:
    """Return top-N most-used augments for a champion (by game count)."""
    rows = conn.execute(
        """
        SELECT
            a.id        AS augment_id,
            a.name      AS augment_name,
            a.rarity,
            COUNT(DISTINCT mp.game_id)                      AS games,
            SUM(CASE WHEN mp.win THEN 1 ELSE 0 END)        AS wins,
            CAST(SUM(CASE WHEN mp.win THEN 1 ELSE 0 END) AS REAL)
                / COUNT(DISTINCT mp.game_id)                AS win_rate
        FROM matches m
        JOIN match_participants mp
            ON mp.game_id = m.game_id AND mp.champion_id = m.champion_id
        JOIN match_augments ma ON ma.participant_id = mp.id
        JOIN augments a ON ma.augment_id = a.id
        WHERE m.champion_id = ?
        GROUP BY a.id, a.name
        ORDER BY games DESC, win_rate DESC
        LIMIT ?
        """,
        (champion_id, limit),
    ).fetchall()

    return [
        {
            "augment_id": row["augment_id"],
            "augment_name": row["augment_name"],
            "rarity": row["rarity"],
            "games": row["games"],
            "wins": row["wins"],
            "win_rate": row["win_rate"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# compute_item_stats
# ---------------------------------------------------------------------------

def compute_item_stats(
    conn: sqlite3.Connection, champion_id: int, item_id: int
) -> dict[str, Any]:
    """Stats for a specific item on a champion (from personal matches).

    Args:
        conn: An open :class:`sqlite3.Connection`.
        champion_id: Champion database ID.
        item_id: Item database ID.

    Returns:
        Dict with ``champion_id``, ``item_id``, ``item_name``,
        ``games``, ``wins``, ``win_rate``.
    """
    # Get item name
    item_name_row = conn.execute(
        "SELECT name FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    item_name = item_name_row["name"] if item_name_row else "Unknown"

    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT mp.game_id)                      AS games,
            SUM(CASE WHEN mp.win THEN 1 ELSE 0 END)        AS wins
        FROM matches m
        JOIN match_participants mp
            ON mp.game_id = m.game_id AND mp.champion_id = m.champion_id
        JOIN match_items mi ON mi.participant_id = mp.id
        WHERE m.champion_id = ? AND mi.item_id = ?
        """,
        (champion_id, item_id),
    ).fetchone()

    games = (row["games"] or 0) if row else 0
    wins = (row["wins"] or 0) if row else 0
    win_rate = (wins / games) if games > 0 else 0.0

    return {
        "champion_id": champion_id,
        "item_id": item_id,
        "item_name": item_name,
        "games": games,
        "wins": wins,
        "win_rate": win_rate,
    }


# ---------------------------------------------------------------------------
# compute_augment_stats
# ---------------------------------------------------------------------------

def compute_augment_stats(
    conn: sqlite3.Connection, champion_id: int, augment_id: int
) -> dict[str, Any]:
    """Stats for a specific augment on a champion (from personal matches).

    Args:
        conn: An open :class:`sqlite3.Connection`.
        champion_id: Champion database ID.
        augment_id: Augment database ID.

    Returns:
        Dict with ``champion_id``, ``augment_id``, ``augment_name``,
        ``rarity``, ``games``, ``wins``, ``win_rate``.
    """
    # Get augment details
    aug_row = conn.execute(
        "SELECT name, rarity FROM augments WHERE id = ?", (augment_id,)
    ).fetchone()
    augment_name = aug_row["name"] if aug_row else "Unknown"
    rarity = aug_row["rarity"] if aug_row else 0

    row = conn.execute(
        """
        SELECT
            COUNT(DISTINCT mp.game_id)                      AS games,
            SUM(CASE WHEN mp.win THEN 1 ELSE 0 END)        AS wins
        FROM matches m
        JOIN match_participants mp
            ON mp.game_id = m.game_id AND mp.champion_id = m.champion_id
        JOIN match_augments ma ON ma.participant_id = mp.id
        WHERE m.champion_id = ? AND ma.augment_id = ?
        """,
        (champion_id, augment_id),
    ).fetchone()

    games = (row["games"] or 0) if row else 0
    wins = (row["wins"] or 0) if row else 0
    win_rate = (wins / games) if games > 0 else 0.0

    return {
        "champion_id": champion_id,
        "augment_id": augment_id,
        "augment_name": augment_name,
        "rarity": rarity,
        "games": games,
        "wins": wins,
        "win_rate": win_rate,
    }


# ---------------------------------------------------------------------------
# compute_all_champion_stats
# ---------------------------------------------------------------------------

def compute_all_champion_stats(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Compute and return stats for all champions the user has played.

    Returns:
        A list of champion stats dicts (same structure as
        :func:`compute_champion_stats`), one per champion that appears
        in the ``matches`` table.
    """
    # Get distinct champion IDs from matches
    champ_rows = conn.execute(
        "SELECT DISTINCT champion_id FROM matches ORDER BY champion_id"
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in champ_rows:
        cid = row["champion_id"]
        stats = compute_champion_stats(conn, cid)
        # Also include champion info
        champ_info = conn.execute(
            "SELECT key, name FROM champions WHERE id = ?", (cid,)
        ).fetchone()
        if champ_info:
            stats["champion_id"] = cid
            stats["champion_key"] = champ_info["key"]
            stats["champion_name"] = champ_info["name"]
        result.append(stats)

    return result


# ---------------------------------------------------------------------------
# sync_riot_matches
# ---------------------------------------------------------------------------

def sync_riot_matches(
    conn: sqlite3.Connection,
    riot_client: RiotAPIClient,
    puuid: str,
    champion_id: int | None = None,
    count: int = 20,
) -> dict[str, Any]:
    """Fetch match history from Riot API and store new matches.

    Only stores Arena matches (queue 1700).  Skips matches that are
    already present in the local database (idempotent).

    Uses :meth:`asyncio.run` internally to call the async Riot client
    from a synchronous context.

    Args:
        conn: An open :class:`sqlite3.Connection`.
        riot_client: Configured :class:`RiotAPIClient` instance.
        puuid: Player's PUUID.
        champion_id: Optional filter — only store matches where the
            player played this champion.
        count: Maximum number of recent Arena match IDs to fetch.

    Returns:
        ``{"new_matches": int, "total_fetched": int}``
    """
    # Fetch match IDs (run async in sync context)
    async def _fetch_ids() -> list[str]:
        return await riot_client.get_match_history(puuid, queue=1700, count=count)

    match_ids = asyncio.run(_fetch_ids())

    new_matches = 0

    for match_id in match_ids:
        # Skip if already stored
        existing = conn.execute(
            "SELECT 1 FROM matches WHERE game_id = ?", (match_id,)
        ).fetchone()
        if existing is not None:
            continue

        # Fetch match detail
        async def _fetch_detail(mid: str) -> dict[str, Any]:
            return await riot_client.get_match_detail(mid)

        try:
            match_data = asyncio.run(_fetch_detail(match_id))
        except Exception:
            logger.exception("Failed to fetch match detail for %s", match_id)
            continue

        # Only store Arena matches (queue 1700)
        info = match_data.get("info", {})
        if info.get("queueId") != 1700:
            continue

        # Store the match
        _store_riot_match(conn, match_data, puuid, champion_id)
        new_matches += 1

    return {
        "new_matches": new_matches,
        "total_fetched": len(match_ids),
    }


def _store_riot_match(
    conn: sqlite3.Connection,
    match_data: dict[str, Any],
    puuid: str,
    champion_id: int | None = None,
) -> None:
    """Parse and store a single Riot match detail into the database.

    Extracts player participant, items, and augments and inserts them
    into ``matches``, ``match_participants``, ``match_items``, and
    ``match_augments``.

    If ``champion_id`` is provided, only stores the match if the player
    played that champion.
    """
    info = match_data.get("info", {})
    metadata = match_data.get("metadata", {})
    game_id = metadata.get("matchId", "")
    game_mode = info.get("gameMode", "CHERRY")
    queue_id = info.get("queueId", 1700)
    game_end_timestamp = info.get("gameEndTimestamp", 0)

    # Convert timestamp (ms since epoch) to ISO string
    try:
        ts = datetime.fromtimestamp(game_end_timestamp / 1000, tz=timezone.utc)
        match_timestamp = ts.isoformat()
    except (OSError, ValueError, OverflowError):
        match_timestamp = None

    participants = info.get("participants", [])

    # Find the player's participant
    player_participant = None
    for p in participants:
        if p.get("puuid") == puuid:
            player_participant = p
            break

    if player_participant is None:
        return

    player_champ_id = player_participant.get("championId", 0)

    # Skip if champion filter doesn't match
    if champion_id is not None and player_champ_id != champion_id:
        return

    player_champ_name = player_participant.get("championName", "")
    placement = player_participant.get("placement", 0)
    win = player_participant.get("win", False)
    kills = player_participant.get("kills", 0)
    deaths = player_participant.get("deaths", 0)
    assists = player_participant.get("assists", 0)

    # Insert into matches table
    conn.execute(
        """
        INSERT OR IGNORE INTO matches
            (game_id, champion_id, champion_key, game_mode, queue_id,
             win, placement, kills, deaths, assists, match_timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            player_champ_id,
            player_champ_name,
            game_mode,
            queue_id,
            1 if win else 0,
            placement,
            kills,
            deaths,
            assists,
            match_timestamp,
        ),
    )

    # Insert all participants
    for p in participants:
        p_champion_id = p.get("championId", 0)
        p_champion_name = p.get("championName", "")
        p_puuid = p.get("puuid", "")
        p_summoner_name = p.get("summonerName", p.get("riotIdGameName", ""))
        p_placement = p.get("placement", 0)
        p_win = p.get("win", False)

        # Get or assign a participant ID (max existing + 1)
        max_id_row = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM match_participants"
        ).fetchone()
        participant_id = max_id_row["next_id"] if max_id_row else 1

        conn.execute(
            """
            INSERT OR IGNORE INTO match_participants
                (id, game_id, puuid, summoner_name, champion_id, champion_key, placement, win)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                participant_id,
                game_id,
                p_puuid,
                p_summoner_name,
                p_champion_id,
                p_champion_name,
                p_placement,
                1 if p_win else 0,
            ),
        )

        # Insert items for this participant
        item_ids = p.get("items", [])
        if isinstance(item_ids, list):
            for slot, item_id in enumerate(item_ids):
                if item_id and item_id != 0:
                    # Ensure item exists in items table (best effort)
                    conn.execute(
                        "INSERT OR IGNORE INTO items(id, name) VALUES (?, ?)",
                        (item_id, f"Item {item_id}"),
                    )
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO match_items
                            (game_id, participant_id, item_id, slot)
                        VALUES (?, ?, ?, ?)
                        """,
                        (game_id, participant_id, item_id, slot),
                    )

        # Insert augments for this participant
        augment_names = p.get("augments", [])
        if isinstance(augment_names, list):
            for slot, aug_api_name in enumerate(augment_names):
                if aug_api_name and aug_api_name != "":
                    # Look up augment ID by api_name
                    aug_row = conn.execute(
                        "SELECT id FROM augments WHERE api_name = ?",
                        (aug_api_name,),
                    ).fetchone()
                    if aug_row is None:
                        # Insert a placeholder augment
                        conn.execute(
                            "INSERT OR IGNORE INTO augments(id, api_name, name) VALUES (?, ?, ?)",
                            (
                                abs(hash(aug_api_name)) % 9000 + 1000,
                                aug_api_name,
                                aug_api_name,
                            ),
                        )
                        aug_row = conn.execute(
                            "SELECT id FROM augments WHERE api_name = ?",
                            (aug_api_name,),
                        ).fetchone()

                    if aug_row:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO match_augments
                                (game_id, participant_id, augment_id, slot)
                            VALUES (?, ?, ?, ?)
                            """,
                            (game_id, participant_id, aug_row["id"], slot),
                        )

    conn.commit()
