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
