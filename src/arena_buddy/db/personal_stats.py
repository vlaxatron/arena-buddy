"""Personal stats computation from local match history.

Computes per-champion-per-item and per-champion-per-augment win rates
from the matches / match_participants / match_items / match_augments tables
and stores results in the personal_item_stats / personal_augment_stats tables.

All functions are idempotent — they clear and rebuild the stats tables
each time so repeated calls produce the same result.
"""

from __future__ import annotations

import sqlite3


def compute_personal_item_stats(conn: sqlite3.Connection) -> None:
    """Compute per-champion per-item stats from local match history.

    Populates the ``personal_item_stats`` table using data from
    ``match_participants`` + ``match_items`` + ``matches``.

    The table is cleared before recomputation (idempotent).

    Args:
        conn: An open :class:`sqlite3.Connection`.
    """
    conn.execute("DELETE FROM personal_item_stats")

    conn.execute("""
        INSERT INTO personal_item_stats (champion_id, item_id, games_played, wins, win_rate)
        SELECT
            mp.champion_id,
            mi.item_id,
            COUNT(DISTINCT mp.game_id) AS games_played,
            SUM(CASE WHEN mp.win THEN 1 ELSE 0 END) AS wins,
            CAST(SUM(CASE WHEN mp.win THEN 1 ELSE 0 END) AS REAL)
                / COUNT(DISTINCT mp.game_id) AS win_rate
        FROM match_participants mp
        JOIN match_items mi ON mp.id = mi.participant_id
        GROUP BY mp.champion_id, mi.item_id
        ORDER BY mp.champion_id, mi.item_id
    """)

    conn.commit()


def compute_personal_augment_stats(conn: sqlite3.Connection) -> None:
    """Compute per-champion per-augment stats from local match history.

    Populates the ``personal_augment_stats`` table using data from
    ``match_participants`` + ``match_augments``.

    The table is cleared before recomputation (idempotent).

    Args:
        conn: An open :class:`sqlite3.Connection`.
    """
    conn.execute("DELETE FROM personal_augment_stats")

    conn.execute("""
        INSERT INTO personal_augment_stats (champion_id, augment_id, games_played, wins, win_rate)
        SELECT
            mp.champion_id,
            ma.augment_id,
            COUNT(DISTINCT mp.game_id) AS games_played,
            SUM(CASE WHEN mp.win THEN 1 ELSE 0 END) AS wins,
            CAST(SUM(CASE WHEN mp.win THEN 1 ELSE 0 END) AS REAL)
                / COUNT(DISTINCT mp.game_id) AS win_rate
        FROM match_participants mp
        JOIN match_augments ma ON mp.id = ma.participant_id
        GROUP BY mp.champion_id, ma.augment_id
        ORDER BY mp.champion_id, ma.augment_id
    """)

    conn.commit()


def recompute_all(conn: sqlite3.Connection) -> None:
    """Recompute both personal item and augment stats.

    Convenience wrapper that calls :func:`compute_personal_item_stats`
    then :func:`compute_personal_augment_stats`.

    Args:
        conn: An open :class:`sqlite3.Connection`.
    """
    compute_personal_item_stats(conn)
    compute_personal_augment_stats(conn)
