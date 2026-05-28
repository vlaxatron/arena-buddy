"""Data access layer — queries for champion items and augments.

All functions accept an open :class:`sqlite3.Connection` with ``row_factory``
set to ``sqlite3.Row`` (or similar dict-like interface).
"""

from __future__ import annotations

import sqlite3
from typing import Any


def get_champion_by_key(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    """Return a champion row by its string key (e.g., ``"Lucian"``).

    Args:
        conn: An open database connection.
        key: Champion key (case-sensitive).

    Returns:
        A dict-like row, or ``None`` if not found.
    """
    row = conn.execute(
        "SELECT id, key, name, icon_filename FROM champions WHERE key = ?", (key,)
    ).fetchone()
    return dict(row) if row else None


def get_items_for_champion(
    conn: sqlite3.Connection,
    champion_id: int,
    patch_id: int,
) -> list[dict[str, Any]]:
    """Return the best items for a champion, sorted by global win rate (descending).

    Each dict includes:
    - ``id``, ``name``, ``icon_filename``, ``gold_cost``
    - ``win_rate``, ``pick_rate``, ``games_played``, ``rank``
    - ``personal_win_rate`` (``None`` when no personal history)
    - ``personal_games`` (``0`` when no personal history)

    Args:
        conn: An open database connection.
        champion_id: Champion database ID.
        patch_id: Patch database ID.

    Returns:
        List of item dicts, best first.
    """
    rows = conn.execute(
        """
        SELECT
            i.id,
            i.name,
            i.icon_filename,
            i.gold_cost,
            gis.win_rate,
            gis.pick_rate,
            gis.games_played,
            gis.rank,
            CAST(NULL AS REAL) AS personal_win_rate,
            0 AS personal_games
        FROM global_item_stats gis
        JOIN items i ON gis.item_id = i.id
        WHERE gis.champion_id = ? AND gis.patch_id = ?
        ORDER BY gis.win_rate DESC
        """,
        (champion_id, patch_id),
    ).fetchall()
    return [dict(row) for row in rows]


def get_augments_for_champion(
    conn: sqlite3.Connection,
    champion_id: int,
    patch_id: int,
) -> dict[str, list[dict[str, Any]]]:
    """Return augments grouped by rarity tier.

    Returns a dict with keys ``"prismatic"``, ``"gold"``, ``"silver"``.
    Each list is ordered by global win rate (descending) within its tier.

    Args:
        conn: An open database connection.
        champion_id: Champion database ID.
        patch_id: Patch database ID.

    Returns:
        ``{"prismatic": [...], "gold": [...], "silver": [...]}``
    """
    rows = conn.execute(
        """
        SELECT
            a.id,
            a.api_name,
            a.name,
            a.rarity,
            a.description,
            a.icon_filename,
            gas.win_rate,
            gas.pick_rate,
            gas.games_played,
            gas.rank,
            CAST(NULL AS REAL) AS personal_win_rate,
            0 AS personal_games
        FROM global_augment_stats gas
        JOIN augments a ON gas.augment_id = a.id
        WHERE gas.champion_id = ? AND gas.patch_id = ?
        ORDER BY gas.rarity DESC, gas.win_rate DESC
        """,
        (champion_id, patch_id),
    ).fetchall()

    result: dict[str, list[dict[str, Any]]] = {
        "prismatic": [],
        "gold": [],
        "silver": [],
    }
    for row in rows:
        d = dict(row)
        rarity = d["rarity"]
        if rarity == 2:
            result["prismatic"].append(d)
        elif rarity == 1:
            result["gold"].append(d)
        elif rarity == 0:
            result["silver"].append(d)

    return result


def get_current_patch(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the current active patch, or ``None`` if none is marked.

    Args:
        conn: An open database connection.

    Returns:
        Dict with ``id``, ``version``, ``scraped_at``, ``is_current``.
    """
    row = conn.execute(
        "SELECT id, version, scraped_at, is_current FROM patches WHERE is_current = 1"
    ).fetchone()
    return dict(row) if row else None


def get_all_champions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all champions in the database.

    Returns:
        List of dicts with ``id``, ``key``, ``name``, ``icon_filename``.
    """
    rows = conn.execute(
        "SELECT id, key, name, icon_filename FROM champions ORDER BY name"
    ).fetchall()
    return [dict(row) for row in rows]


def search_champions(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """Search champions by name or key (case-insensitive, partial match).

    Args:
        conn: An open database connection.
        query: Search string (matched case-insensitively against name and key).

    Returns:
        List of matching champion dicts ordered by name.
    """
    pattern = f"%{query}%"
    rows = conn.execute(
        "SELECT id, key, name, icon_filename FROM champions "
        "WHERE name LIKE ? OR key LIKE ? "
        "ORDER BY name",
        (pattern, pattern),
    ).fetchall()
    return [dict(row) for row in rows]


def list_matches(
    conn: sqlite3.Connection,
    champion_key: str | None = None,
    placement: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List matches with optional filters and pagination.

    Args:
        conn: An open database connection.
        champion_key: Optional filter by champion key.
        placement: Optional filter by placement (1-4).
        limit: Maximum number of matches to return.
        offset: Number of matches to skip.

    Returns:
        List of match dicts ordered by match_timestamp descending.
    """
    clauses = ["1=1"]
    params: list[Any] = []

    if champion_key:
        clauses.append("m.champion_key = ?")
        params.append(champion_key)
    if placement is not None:
        clauses.append("m.placement = ?")
        params.append(placement)

    where = " AND ".join(clauses)
    params.extend([limit, offset])

    rows = conn.execute(
        f"""
        SELECT
            m.game_id,
            m.champion_key,
            m.game_mode,
            m.win,
            m.placement,
            m.duration_sec,
            m.kills,
            m.deaths,
            m.assists,
            m.match_timestamp,
            m.patch_version,
            c.name AS champion_name,
            c.icon_filename AS champion_icon
        FROM matches m
        JOIN champions c ON m.champion_id = c.id
        WHERE {where}
        ORDER BY m.match_timestamp DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()

    matches = []
    for row in rows:
        d = dict(row)
        # Get partner info for each match
        partner_row = conn.execute(
            """
            SELECT mp.champion_key, mp.summoner_name, c.name AS champion_name
            FROM match_participants mp
            JOIN champions c ON mp.champion_id = c.id
            WHERE mp.game_id = ? AND mp.champion_key != ?
            LIMIT 1
            """,
            (d["game_id"], d["champion_key"]),
        ).fetchone()
        d["partner"] = dict(partner_row) if partner_row else None
        matches.append(d)

    return matches


def count_matches(
    conn: sqlite3.Connection,
    champion_key: str | None = None,
    placement: int | None = None,
) -> int:
    """Count total matches matching optional filters.

    Args:
        conn: An open database connection.
        champion_key: Optional filter by champion key.
        placement: Optional filter by placement (1-4).

    Returns:
        Total match count.
    """
    clauses = ["1=1"]
    params: list[Any] = []

    if champion_key:
        clauses.append("champion_key = ?")
        params.append(champion_key)
    if placement is not None:
        clauses.append("placement = ?")
        params.append(placement)

    where = " AND ".join(clauses)
    row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM matches WHERE {where}",
        params,
    ).fetchone()
    return row["cnt"] if row else 0


def get_match_detail(
    conn: sqlite3.Connection,
    match_id: str,
) -> dict[str, Any] | None:
    """Return full match detail with participants, items, and augments.

    Args:
        conn: An open database connection.
        match_id: The game_id of the match.

    Returns:
        Full match detail dict, or None if not found.
    """
    match_row = conn.execute(
        """
        SELECT
            m.game_id,
            m.champion_id,
            m.champion_key,
            m.game_mode,
            m.queue_id,
            m.map_id,
            m.win,
            m.placement,
            m.duration_sec,
            m.kills,
            m.deaths,
            m.assists,
            m.match_timestamp,
            m.patch_version,
            c.name AS champion_name,
            c.icon_filename AS champion_icon
        FROM matches m
        JOIN champions c ON m.champion_id = c.id
        WHERE m.game_id = ?
        """,
        (match_id,),
    ).fetchone()

    if match_row is None:
        return None

    match = dict(match_row)

    # Get all participants
    participant_rows = conn.execute(
        """
        SELECT
            mp.id,
            mp.puuid,
            mp.summoner_name,
            mp.champion_id,
            mp.champion_key,
            mp.placement,
            mp.win,
            c.name AS champion_name,
            c.icon_filename AS champion_icon
        FROM match_participants mp
        JOIN champions c ON mp.champion_id = c.id
        WHERE mp.game_id = ?
        ORDER BY mp.placement
        """,
        (match_id,),
    ).fetchall()

    participants = []
    for prow in participant_rows:
        pdict = dict(prow)

        # Get items for this participant
        item_rows = conn.execute(
            """
            SELECT
                mi.slot,
                i.id AS item_id,
                i.name AS item_name,
                i.icon_filename
            FROM match_items mi
            JOIN items i ON mi.item_id = i.id
            WHERE mi.game_id = ? AND mi.participant_id = ?
            ORDER BY mi.slot
            """,
            (match_id, pdict["id"]),
        ).fetchall()
        pdict["items"] = [dict(ir) for ir in item_rows]

        # Get augments for this participant
        augment_rows = conn.execute(
            """
            SELECT
                ma.slot,
                a.id AS augment_id,
                a.api_name,
                a.name AS augment_name,
                a.rarity,
                a.description,
                a.icon_filename
            FROM match_augments ma
            JOIN augments a ON ma.augment_id = a.id
            WHERE ma.game_id = ? AND ma.participant_id = ?
            ORDER BY ma.slot
            """,
            (match_id, pdict["id"]),
        ).fetchall()
        pdict["augments"] = [dict(ar) for ar in augment_rows]

        participants.append(pdict)

    match["participants"] = participants
    return match


def get_match_stats(
    conn: sqlite3.Connection,
    champion_key: str | None = None,
) -> dict[str, Any]:
    """Get aggregate match stats (total matches, win rate, avg placement).

    Args:
        conn: An open database connection.
        champion_key: Optional filter by champion key.

    Returns:
        Dict with total_matches, wins, win_rate, avg_placement.
    """
    clauses = ["1=1"]
    params: list[Any] = []

    if champion_key:
        clauses.append("champion_key = ?")
        params.append(champion_key)

    where = " AND ".join(clauses)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total_matches,
            SUM(CASE WHEN win = 1 THEN 1 ELSE 0 END) AS wins,
            AVG(placement) AS avg_placement
        FROM matches
        WHERE {where}
        """,
        params,
    ).fetchone()

    total = row["total_matches"] if row else 0
    wins = row["wins"] if row else 0
    avg_place = row["avg_placement"] if row else None

    return {
        "total_matches": total,
        "wins": wins,
        "win_rate": round(wins / total, 4) if total > 0 else 0.0,
        "avg_placement": round(avg_place, 2) if avg_place is not None else None,
    }
