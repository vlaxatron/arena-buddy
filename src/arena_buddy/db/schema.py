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
    description TEXT,
    is_prismatic BOOLEAN DEFAULT 0
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
-- MATCH HISTORY (captured from LCU)
-- ============================================================

CREATE TABLE IF NOT EXISTS matches (
    game_id         TEXT PRIMARY KEY,
    champion_id     INTEGER NOT NULL,
    champion_key    TEXT NOT NULL,
    game_mode       TEXT NOT NULL,          -- e.g., "CHERRY", "CLASSIC"
    queue_id        INTEGER,
    map_id          INTEGER,
    win             BOOLEAN NOT NULL,
    placement       INTEGER,               -- 1-4 in Arena
    duration_sec    INTEGER,
    kills           INTEGER,
    deaths          INTEGER,
    assists         INTEGER,
    match_timestamp TIMESTAMP,
    patch_version   TEXT,
    raw_json        TEXT,                   -- full match detail JSON
    FOREIGN KEY (champion_id) REFERENCES champions(id)
);

CREATE TABLE IF NOT EXISTS match_participants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    puuid           TEXT,
    summoner_name   TEXT,
    champion_id     INTEGER NOT NULL,
    champion_key    TEXT NOT NULL,
    placement       INTEGER,
    win             BOOLEAN,
    FOREIGN KEY (game_id) REFERENCES matches(game_id),
    FOREIGN KEY (champion_id) REFERENCES champions(id)
);

CREATE TABLE IF NOT EXISTS match_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    participant_id  INTEGER NOT NULL,
    item_id         INTEGER NOT NULL,
    slot            INTEGER,
    FOREIGN KEY (game_id) REFERENCES matches(game_id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (participant_id) REFERENCES match_participants(id)
);

CREATE TABLE IF NOT EXISTS match_augments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         TEXT NOT NULL,
    participant_id  INTEGER NOT NULL,
    augment_id      INTEGER NOT NULL,
    slot            INTEGER,
    FOREIGN KEY (game_id) REFERENCES matches(game_id),
    FOREIGN KEY (augment_id) REFERENCES augments(id),
    FOREIGN KEY (participant_id) REFERENCES match_participants(id)
);

-- ============================================================
-- PERSONAL STATS (computed from local match history)
-- ============================================================

CREATE TABLE IF NOT EXISTS personal_item_stats (
    champion_id INTEGER NOT NULL,
    item_id     INTEGER NOT NULL,
    games_played INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    win_rate    REAL,
    PRIMARY KEY (champion_id, item_id),
    FOREIGN KEY (champion_id) REFERENCES champions(id),
    FOREIGN KEY (item_id)     REFERENCES items(id)
);

CREATE TABLE IF NOT EXISTS personal_augment_stats (
    champion_id INTEGER NOT NULL,
    augment_id  INTEGER NOT NULL,
    games_played INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    win_rate    REAL,
    PRIMARY KEY (champion_id, augment_id),
    FOREIGN KEY (champion_id) REFERENCES champions(id),
    FOREIGN KEY (augment_id)  REFERENCES augments(id)
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
