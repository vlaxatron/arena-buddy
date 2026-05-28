"""SQLite schema creation for Arena Buddy.

Uses raw ``IF NOT EXISTS`` DDL — safe to call repeatedly (idempotent).
"""

from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
-- ============================================================
-- STATIC DATA (from Data Dragon / CommunityDragon)
-- ============================================================

CREATE TABLE IF NOT EXISTS champions (
    id          INTEGER PRIMARY KEY,
    key         TEXT    NOT NULL UNIQUE,   -- e.g., "Lucian"
    name        TEXT    NOT NULL,          -- e.g., "Lucian"
    icon_filename TEXT                     -- local filename in cache/
);

CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    icon_filename TEXT,
    gold_cost   INTEGER,
    description TEXT
);

CREATE TABLE IF NOT EXISTS augments (
    id          INTEGER PRIMARY KEY,
    api_name    TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    rarity      INTEGER,                  -- 0=Silver, 1=Gold, 2=Prismatic, 4=Special
    description TEXT,
    icon_filename TEXT
);

-- Patches (tracked for stats versioning)
CREATE TABLE IF NOT EXISTS patches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     TEXT    NOT NULL UNIQUE,   -- e.g., "16.11"
    scraped_at  TIMESTAMP,
    is_current  BOOLEAN DEFAULT 0
);

-- ============================================================
-- GLOBAL STATS (scraped from LoLalytics)
-- ============================================================

CREATE TABLE IF NOT EXISTS global_item_stats (
    champion_id INTEGER NOT NULL,
    item_id     INTEGER NOT NULL,
    patch_id    INTEGER NOT NULL,
    win_rate    REAL,                      -- e.g., 0.5432
    pick_rate   REAL,                      -- e.g., 0.1234
    games_played INTEGER,
    rank        INTEGER,                   -- position in recommendation list
    PRIMARY KEY (champion_id, item_id, patch_id),
    FOREIGN KEY (champion_id) REFERENCES champions(id),
    FOREIGN KEY (item_id)     REFERENCES items(id),
    FOREIGN KEY (patch_id)    REFERENCES patches(id)
);

CREATE TABLE IF NOT EXISTS global_augment_stats (
    champion_id INTEGER NOT NULL,
    augment_id  INTEGER NOT NULL,
    patch_id    INTEGER NOT NULL,
    rarity      INTEGER,
    win_rate    REAL,
    pick_rate   REAL,
    games_played INTEGER,
    rank        INTEGER,
    PRIMARY KEY (champion_id, augment_id, patch_id),
    FOREIGN KEY (champion_id) REFERENCES champions(id),
    FOREIGN KEY (augment_id)  REFERENCES augments(id),
    FOREIGN KEY (patch_id)    REFERENCES patches(id)
);
"""


def create_all(conn: sqlite3.Connection) -> None:
    """Create all tables in *conn* (idempotent — safe to call repeatedly).

    Args:
        conn: An open :class:`sqlite3.Connection`.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
