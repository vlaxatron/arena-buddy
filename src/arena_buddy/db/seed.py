"""Seed data for Phase 1 MVP — Lucian Arena recommendations.

Inserts hardcoded champion, item, augment, and global stats data.
All INSERTs use ``INSERT OR IGNORE`` (or ``INSERT ... ON CONFLICT DO NOTHING``
for the composite-PK tables) so the module is idempotent.

When Data Dragon / CommunityDragon JSON files are present in the cache
directory (``~/.cache/arena-buddy/data/``), the importer is called first
to populate the database with the full dataset before the hardcoded
fallback seed data is applied.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Lucian data
# ---------------------------------------------------------------------------

LUCIAN = (236, "Lucian", "Lucian", "Lucian.png")

ITEMS = [
    (6672, "Kraken Slayer", "6672.png", 3100, "Every third attack deals bonus magic damage."),
    (6675, "Navori Flickerblade", "6675.png", 2600, "Attacks reduce non-ultimate cooldowns."),
    (3031, "Infinity Edge", "3031.png", 3400, "Critical strikes deal bonus damage."),
    (3072, "Bloodthirster", "3072.png", 3400, "Lifesteal and overheal shield."),
    (3036, "Lord Dominik's Regards", "3036.png", 3000, "Bonus armor penetration."),
    (3026, "Guardian Angel", "3026.png", 3200, "Revive on death."),
    (3006, "Berserker's Greaves", "3006.png", 1100, "Attack speed boots."),
    (3139, "Mercurial Scimitar", "3139.png", 3000, "CC removal active + crit."),
]

AUGMENTS = [
    # Prismatic (rarity=2)
    (101, "BackToBasics", "Back To Basics", 2,
     "Your basic abilities deal massively increased damage, but your ultimate is disabled.",
     "BackToBasics.png"),
    (102, "BladeWaltz", "Blade Waltz", 2,
     "Become untargetable and dash through enemies dealing damage.",
     "BladeWaltz.png"),
    (103, "SymphonyOfWar", "Symphony of War", 2,
     "Gain massive attack speed and on-hit damage.",
     "SymphonyOfWar.png"),
    # Gold (rarity=1)
    (201, "ADAPt", "ADAPt", 1,
     "Gain adaptive force based on your items.",
     "ADAPt.png"),
    (202, "BuffBuddies", "Buff Buddies", 1,
     "Buffs you apply to allies are stronger.",
     "BuffBuddies.png"),
    (203, "BreadAndButter", "Bread And Butter", 1,
     "Your most-used ability deals bonus damage.",
     "BreadAndButter.png"),
    (204, "Vulnerability", "Vulnerability", 1,
     "Damaging enemies makes them take increased damage.",
     "Vulnerability.png"),
    # Silver (rarity=0)
    (301, "Stats", "Stats!", 0,
     "Gain a small amount of all stats.",
     "Stats.png"),
    (302, "WarmupRoutine", "Warmup Routine", 0,
     "Gain increasing stats over the first minutes of combat.",
     "WarmupRoutine.png"),
    (303, "TankItOrLeaveIt", "Tank It Or Leave It", 0,
     "Gain bonus resistances when below 50% health.",
     "TankItOrLeaveIt.png"),
]

# (champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank)
ITEM_STATS = [
    (236, 6672, 1, 0.562, 0.384, 12400, 1),   # Kraken Slayer
    (236, 6675, 1, 0.558, 0.421, 13600, 2),   # Navori
    (236, 3031, 1, 0.549, 0.289, 9300,  3),   # IE
    (236, 3072, 1, 0.541, 0.223, 7200,  4),   # BT
    (236, 3036, 1, 0.537, 0.185, 6000,  5),   # LDR
    (236, 3026, 1, 0.532, 0.158, 5100,  6),   # GA
    (236, 3006, 1, 0.528, 0.652, 21000, 7),   # Greaves
    (236, 3139, 1, 0.515, 0.084, 2700,  8),   # Mercurial
]

# (champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games, rank)
AUGMENT_STATS = [
    # Prismatic
    (236, 101, 1, 2, 0.632, 0.124, 4200, 1),   # Back To Basics
    (236, 102, 1, 2, 0.618, 0.087, 3100, 2),   # Blade Waltz
    (236, 103, 1, 2, 0.594, 0.101, 3600, 3),   # Symphony of War
    # Gold
    (236, 201, 1, 1, 0.584, 0.182, 6200, 1),   # ADAPt
    (236, 202, 1, 1, 0.571, 0.143, 4900, 2),   # Buff Buddies
    (236, 203, 1, 1, 0.563, 0.228, 7800, 3),   # Bread And Butter
    (236, 204, 1, 1, 0.557, 0.165, 5600, 4),   # Vulnerability
    # Silver
    (236, 301, 1, 0, 0.532, 0.284, 9800, 1),   # Stats!
    (236, 302, 1, 0, 0.521, 0.192, 6600, 2),   # Warmup Routine
    (236, 303, 1, 0, 0.508, 0.113, 3900, 3),   # Tank It Or Leave It
]

PATCH = ("16.11",)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def seed_all(conn: sqlite3.Connection) -> None:
    """Insert all seed data into *conn* (idempotent — safe to call repeatedly).

    If Data Dragon / CommunityDragon JSON files are found in the cache
    directory they are imported first, providing the full dataset.
    Hardcoded fallback data is always applied afterward (INSERT OR IGNORE
    ensures no duplicates).

    Args:
        conn: An open :class:`sqlite3.Connection`.
    """
    _seed_from_files(conn)
    _seed_champions(conn)
    _seed_items(conn)
    _seed_augments(conn)
    _seed_patch(conn)
    _seed_global_stats(conn)
    conn.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Known cache location for Data Dragon / CommunityDragon data files
_CACHE_DIR = Path.home() / ".cache" / "arena-buddy" / "data"
_CHAMPIONS_FILE = "champions.json"
_ITEMS_FILE = "items.json"
_AUGMENTS_FILE = "augments.json"


def _seed_from_files(conn: sqlite3.Connection) -> None:
    """Import full dataset from cache files if they exist.

    Looks for ``champions.json``, ``items.json``, and ``augments.json`` in
    ``~/.cache/arena-buddy/data/``.  Missing files are silently skipped
    (the hardcoded fallback data will still be applied).  Malformed files
    raise :class:`ValueError`.
    """
    from arena_buddy.db.importer import import_all  # local import

    champions_path = _CACHE_DIR / _CHAMPIONS_FILE
    items_path = _CACHE_DIR / _ITEMS_FILE
    augments_path = _CACHE_DIR / _AUGMENTS_FILE

    # Only call the importer if all three files exist
    if champions_path.exists() and items_path.exists() and augments_path.exists():
        import_all(conn, champions_path, items_path, augments_path)


def _seed_champions(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO champions (id, key, name, icon_filename) VALUES (?, ?, ?, ?)",
        LUCIAN,
    )


def _seed_items(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO items (id, name, icon_filename, gold_cost, description) "
        "VALUES (?, ?, ?, ?, ?)",
        ITEMS,
    )


def _seed_augments(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO augments (id, api_name, name, rarity, description, icon_filename) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        AUGMENTS,
    )


def _seed_patch(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO patches (version, is_current) VALUES (?, 1)",
        PATCH,
    )


def _seed_global_stats(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO global_item_stats "
        "(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ITEM_STATS,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO global_augment_stats "
        "(champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games_played, rank) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        AUGMENT_STATS,
    )
