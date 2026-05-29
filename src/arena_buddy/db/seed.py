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
    # --- Lucian (236) ---
    (236, 6672, 1, 0.562, 0.384, 12400, 1),   # Kraken Slayer
    (236, 6675, 1, 0.558, 0.421, 13600, 2),   # Navori
    (236, 3031, 1, 0.549, 0.289, 9300,  3),   # IE
    (236, 3072, 1, 0.541, 0.223, 7200,  4),   # BT
    (236, 3036, 1, 0.537, 0.185, 6000,  5),   # LDR
    (236, 3026, 1, 0.532, 0.158, 5100,  6),   # GA
    (236, 3006, 1, 0.528, 0.652, 21000, 7),   # Berserker's Greaves
    (236, 3009, 1, 0.523, 0.218, 7000,  8),   # Boots of Swiftness
    (236, 3020, 1, 0.518, 0.143, 4600,  9),   # Sorcerer's Shoes
    (236, 3139, 1, 0.515, 0.084, 2700,  10),  # Mercurial
    # --- Zed (238) ---
    (238, 6692, 1, 0.571, 0.412, 11800, 1),   # Eclipse
    (238, 3142, 1, 0.563, 0.389, 10400, 2),   # Youmuu's
    (238, 6694, 1, 0.554, 0.335, 8900,  3),   # Serylda's
    (238, 3156, 1, 0.548, 0.298, 7200,  4),   # Maw
    (238, 3074, 1, 0.542, 0.261, 6700,  5),   # Ravenous
    (238, 6333, 1, 0.539, 0.224, 5800,  6),   # Death's Dance
    (238, 3009, 1, 0.551, 0.445, 14200, 7),   # Boots of Swiftness
    (238, 3006, 1, 0.532, 0.512, 16400, 8),   # Berserker's Greaves
    (238, 3111, 1, 0.526, 0.188, 6000,  9),   # Mercury's Treads
    (238, 3078, 1, 0.522, 0.172, 5500,  10),  # Trinity Force
    # --- Sett (875) ---
    (875, 3078, 1, 0.572, 0.398, 11200, 1),   # Trinity Force
    (875, 3053, 1, 0.565, 0.356, 9800,  2),   # Sterak's
    (875, 3071, 1, 0.558, 0.334, 9200,  3),   # Black Cleaver
    (875, 3068, 1, 0.551, 0.288, 7800,  4),   # Sunfire
    (875, 3742, 1, 0.547, 0.274, 7300,  5),   # Dead Man's
    (875, 3193, 1, 0.543, 0.249, 6800,  6),   # Gargoyle
    (875, 3047, 1, 0.561, 0.482, 15200, 7),   # Plated Steelcaps
    (875, 3111, 1, 0.538, 0.312, 10000, 8),   # Mercury's Treads
    (875, 3009, 1, 0.531, 0.195, 6200,  9),   # Boots of Swiftness
    (875, 3156, 1, 0.527, 0.158, 5100,  10),  # Maw
    # --- Aatrox (266) ---
    (266, 3074, 1, 0.568, 0.388, 10600, 1),   # Ravenous
    (266, 6692, 1, 0.562, 0.354, 9500,  2),   # Eclipse
    (266, 6333, 1, 0.557, 0.322, 8700,  3),   # Death's Dance
    (266, 3071, 1, 0.552, 0.298, 8000,  4),   # Black Cleaver
    (266, 3156, 1, 0.548, 0.274, 7400,  5),   # Maw
    (266, 6694, 1, 0.544, 0.241, 6500,  6),   # Serylda's
    (266, 3047, 1, 0.558, 0.468, 14800, 7),   # Plated Steelcaps
    (266, 3111, 1, 0.534, 0.288, 9200,  8),   # Mercury's Treads
    (266, 3009, 1, 0.528, 0.172, 5500,  9),   # Boots of Swiftness
    (266, 3742, 1, 0.525, 0.162, 5200,  10),  # Dead Man's
    # --- Yasuo (157) ---
    (157, 3031, 1, 0.574, 0.512, 16200, 1),   # IE
    (157, 6672, 1, 0.568, 0.445, 14200, 2),   # Kraken Slayer
    (157, 3046, 1, 0.562, 0.389, 12400, 3),   # Phantom Dancer
    (157, 3072, 1, 0.557, 0.342, 11000, 4),   # BT
    (157, 3153, 1, 0.551, 0.288, 9200,  5),   # BORK
    (157, 3036, 1, 0.548, 0.224, 7200,  6),   # LDR
    (157, 3006, 1, 0.555, 0.582, 18600, 7),   # Berserker's Greaves
    (157, 3009, 1, 0.532, 0.245, 7800,  8),   # Boots of Swiftness
    (157, 3047, 1, 0.526, 0.192, 6100,  9),   # Plated Steelcaps
    (157, 6333, 1, 0.522, 0.172, 5500,  10),  # Death's Dance
    # --- Kai'Sa (145) ---
    (145, 6672, 1, 0.571, 0.482, 15200, 1),   # Kraken Slayer
    (145, 3085, 1, 0.565, 0.388, 12400, 2),   # Runaan's
    (145, 6675, 1, 0.561, 0.354, 11300, 3),   # Navori
    (145, 3124, 1, 0.558, 0.322, 10300, 4),   # Guinsoo's
    (145, 3153, 1, 0.554, 0.298, 9500,  5),   # BORK
    (145, 3031, 1, 0.551, 0.254, 8100,  6),   # IE
    (145, 3006, 1, 0.548, 0.568, 18200, 7),   # Berserker's Greaves
    (145, 3009, 1, 0.532, 0.234, 7500,  8),   # Boots of Swiftness
    (145, 3020, 1, 0.527, 0.188, 6000,  9),   # Sorcerer's Shoes
    (145, 3139, 1, 0.524, 0.154, 4900,  10),  # Mercurial
]

# Augment stats — generated for all 6 champions
# (champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games, rank)
import random
random.seed(42)

# Base augment stats per augment (augment_id, rarity, base_wr, base_pr, base_games, rank)
_AUG_BASES = [
    # Prismatic
    (101, 2, 0.632, 0.124, 4200, 1),
    (102, 2, 0.618, 0.087, 3100, 2),
    (103, 2, 0.594, 0.101, 3600, 3),
    # Gold
    (201, 1, 0.584, 0.182, 6200, 1),
    (202, 1, 0.571, 0.143, 4900, 2),
    (203, 1, 0.563, 0.228, 7800, 3),
    (204, 1, 0.557, 0.165, 5600, 4),
    # Silver
    (301, 0, 0.532, 0.284, 9800, 1),
    (302, 0, 0.521, 0.192, 6600, 2),
    (303, 0, 0.508, 0.113, 3900, 3),
]

# Champions: Lucian, Zed, Sett, Aatrox, Yasuo, Kai'Sa
_AUG_CHAMPS = [236, 238, 875, 266, 157, 145]

AUGMENT_STATS = []
for cid in _AUG_CHAMPS:
    for aug_id, rarity, base_wr, base_pr, base_games, rank in _AUG_BASES:
        wr = base_wr + random.uniform(-0.04, 0.04)
        pr = base_pr + random.uniform(-0.03, 0.03)
        games = int(base_games * random.uniform(0.7, 1.5))
        AUGMENT_STATS.append((cid, aug_id, 1, rarity, round(wr, 4), round(pr, 4), games, rank))

# --- AT THIS POINT, random module is already imported ---
# Keep seeding for the prismatic items below

# Prismatic item stats — seeded for all 6 champions
# Each champion gets the same set of prismatic items but with different WR
PRISMATIC_ITEM_STATS = []
_champs = [236, 238, 875, 266, 157, 145]  # Lucian, Zed, Sett, Aatrox, Yasuo, Kai'Sa
_pris_items = [
    (447103, 0.671),  # Hemomancer's Helm
    (446632, 0.665),  # Divine Sunderer
    (223069, 0.662),  # Void Immolation
    (228006, 0.655),  # Sanguine Blade
    (447113, 0.651),  # Detonation Orb
    (446656, 0.648),  # Everfrost
    (447114, 0.642),  # Reverberation
    (447121, 0.635),  # Twilight's Edge
]
for cid in _champs:
    rank = 1
    for item_id, base_wr in _pris_items:
        # Add slight per-champion variation (±3%)
        wr = base_wr + random.uniform(-0.03, 0.03)
        pr = random.uniform(0.05, 0.20)
        games = int(random.uniform(800, 4000))
        PRISMATIC_ITEM_STATS.append((cid, item_id, 1, round(wr, 4), round(pr, 4), games, rank))
        rank += 1

PATCH = ("16.11",)


def _mark_prismatic_items(conn: sqlite3.Connection) -> None:
    """Mark known Arena prismatic items in the items table.

    Prismatic items are Arena-exclusive legendary gear (not to be confused
    with Prismatic Augments).  The list is curated from Data Dragon analysis
    (items enabled on map 30 but not on map 11, with gold cost ≥2500).
    """
    # Full list from reference doc — 50 Arena-exclusive prismatic items
    prismatic_ids = [
        3430, 4015, 4016, 4017,          # Legacy/Returning
        220012, 224004, 226630, 226653, 226675,  # Arena-specific 22xxxx
        223069, 228002, 228003, 228004, 228005, 228006, 228008,  # High-cost
        443054, 443055, 443061, 443062, 443063, 443064, 443069, 443079, 443081, 443090,  # Core 443xxx
        446632, 446656, 446667, 446671, 446691,  # Returning mythics
        447100, 447102, 447103, 447104, 447105, 447106, 447107, 447108, 447110,  # Signature 447xxx
        447113, 447114, 447115, 447116, 447118, 447119, 447120, 447121, 447122, 447123,
    ]
    placeholders = ','.join('?' * len(prismatic_ids))
    conn.execute(
        f'UPDATE items SET is_prismatic = 1 WHERE id IN ({placeholders})',
        prismatic_ids,
    )


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
    _mark_prismatic_items(conn)
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
        "INSERT OR IGNORE INTO global_item_stats "
        "(champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        PRISMATIC_ITEM_STATS,
    )
    # NOTE: Augment seed data removed — Qwik scraper now provides real augment
    # win rates from LoLalytics. The old fabricated seed augment stats (IDs 101-303)
    # are no longer inserted.
