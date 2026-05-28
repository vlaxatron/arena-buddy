"""Tests for arena_buddy.db.personal_stats — Personal stats computation."""

from __future__ import annotations

import sqlite3

import pytest

from arena_buddy.db.schema import create_all


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_matches(temp_db_path):
    """Database with schema + match data for stats computation."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_all(conn)

    # Seed champions and items needed for FK references
    conn.execute(
        "INSERT OR IGNORE INTO champions(id, key, name) VALUES (236, 'Lucian', 'Lucian')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO champions(id, key, name) VALUES (24, 'Jax', 'Jax')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO items(id, name) VALUES (3031, 'Infinity Edge')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO items(id, name) VALUES (6694, 'Quickblades')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO items(id, name) VALUES (3153, 'Blade of the Ruined King')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO augments(id, api_name, name, rarity) VALUES (1001, 'AugA', 'Augment A', 0)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO augments(id, api_name, name, rarity) VALUES (2001, 'AugB', 'Augment B', 1)"
    )

    # Insert 3 matches: 2 wins, 1 loss — Lucian with IE in 3 games (2 wins)
    # Win 1
    conn.execute(
        """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement)
           VALUES ('game_1', 236, 'Lucian', 'CHERRY', 1, 1)"""
    )
    conn.execute(
        """INSERT INTO match_participants(id, game_id, champion_id, champion_key, win)
           VALUES (1, 'game_1', 236, 'Lucian', 1)"""
    )
    conn.execute(
        """INSERT INTO match_items(game_id, participant_id, item_id, slot)
           VALUES ('game_1', 1, 3031, 0)"""
    )
    conn.execute(
        """INSERT INTO match_items(game_id, participant_id, item_id, slot)
           VALUES ('game_1', 1, 6694, 1)"""
    )
    conn.execute(
        """INSERT INTO match_augments(game_id, participant_id, augment_id, slot)
           VALUES ('game_1', 1, 1001, 0)"""
    )
    conn.execute(
        """INSERT INTO match_augments(game_id, participant_id, augment_id, slot)
           VALUES ('game_1', 1, 2001, 1)"""
    )

    # Win 2
    conn.execute(
        """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement)
           VALUES ('game_2', 236, 'Lucian', 'CHERRY', 1, 1)"""
    )
    conn.execute(
        """INSERT INTO match_participants(id, game_id, champion_id, champion_key, win)
           VALUES (2, 'game_2', 236, 'Lucian', 1)"""
    )
    conn.execute(
        """INSERT INTO match_items(game_id, participant_id, item_id, slot)
           VALUES ('game_2', 2, 3031, 0)"""
    )
    conn.execute(
        """INSERT INTO match_augments(game_id, participant_id, augment_id, slot)
           VALUES ('game_2', 2, 1001, 0)"""
    )

    # Loss 3
    conn.execute(
        """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement)
           VALUES ('game_3', 236, 'Lucian', 'CHERRY', 0, 3)"""
    )
    conn.execute(
        """INSERT INTO match_participants(id, game_id, champion_id, champion_key, win)
           VALUES (3, 'game_3', 236, 'Lucian', 0)"""
    )
    conn.execute(
        """INSERT INTO match_items(game_id, participant_id, item_id, slot)
           VALUES ('game_3', 3, 3031, 0)"""
    )
    conn.execute(
        """INSERT INTO match_items(game_id, participant_id, item_id, slot)
           VALUES ('game_3', 3, 3153, 1)"""
    )
    conn.execute(
        """INSERT INTO match_augments(game_id, participant_id, augment_id, slot)
           VALUES ('game_3', 3, 2001, 0)"""
    )

    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Personal item stats tests
# ---------------------------------------------------------------------------

class TestComputePersonalItemStats:
    """Tests for compute_personal_item_stats()."""

    def test_item_stats_populated(self, db_with_matches: sqlite3.Connection) -> None:
        """Item stats table gets populated from match data."""
        from arena_buddy.db.personal_stats import compute_personal_item_stats

        compute_personal_item_stats(db_with_matches)

        rows = db_with_matches.execute(
            "SELECT * FROM personal_item_stats ORDER BY item_id"
        ).fetchall()
        assert len(rows) >= 1

    def test_infinity_edge_win_rate(self, db_with_matches: sqlite3.Connection) -> None:
        """IE appears in 3 games (2 wins, 1 loss) => ~66.7% win rate."""
        from arena_buddy.db.personal_stats import compute_personal_item_stats

        compute_personal_item_stats(db_with_matches)

        row = db_with_matches.execute(
            "SELECT * FROM personal_item_stats WHERE champion_id = 236 AND item_id = 3031"
        ).fetchone()
        assert row is not None
        assert row["games_played"] == 3
        assert row["wins"] == 2
        assert abs(row["win_rate"] - (2 / 3)) < 0.01

    def test_item_stats_idempotent(self, db_with_matches: sqlite3.Connection) -> None:
        """Running computation twice doesn't double counts."""
        from arena_buddy.db.personal_stats import compute_personal_item_stats

        compute_personal_item_stats(db_with_matches)
        compute_personal_item_stats(db_with_matches)

        row = db_with_matches.execute(
            "SELECT * FROM personal_item_stats WHERE champion_id = 236 AND item_id = 3031"
        ).fetchone()
        assert row is not None
        assert row["games_played"] == 3  # not 6

    def test_champion_separation(self, db_with_matches: sqlite3.Connection) -> None:
        """Stats are separated by champion."""
        # Add a Jax game
        db_with_matches.execute(
            """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement)
               VALUES ('game_4', 24, 'Jax', 'CHERRY', 1, 1)"""
        )
        db_with_matches.execute(
            """INSERT INTO match_participants(id, game_id, champion_id, champion_key, win)
               VALUES (4, 'game_4', 24, 'Jax', 1)"""
        )
        db_with_matches.execute(
            """INSERT INTO match_items(game_id, participant_id, item_id, slot)
               VALUES ('game_4', 4, 3031, 0)"""
        )
        db_with_matches.commit()

        from arena_buddy.db.personal_stats import compute_personal_item_stats

        compute_personal_item_stats(db_with_matches)

        lucian_row = db_with_matches.execute(
            "SELECT * FROM personal_item_stats WHERE champion_id = 236 AND item_id = 3031"
        ).fetchone()
        jax_row = db_with_matches.execute(
            "SELECT * FROM personal_item_stats WHERE champion_id = 24 AND item_id = 3031"
        ).fetchone()

        assert lucian_row is not None
        assert jax_row is not None
        assert lucian_row["games_played"] == 3  # Lucian's 3 games
        assert jax_row["games_played"] == 1  # Jax's 1 game


# ---------------------------------------------------------------------------
# Personal augment stats tests
# ---------------------------------------------------------------------------

class TestComputePersonalAugmentStats:
    """Tests for compute_personal_augment_stats()."""

    def test_augment_stats_populated(self, db_with_matches: sqlite3.Connection) -> None:
        """Augment stats table gets populated from match data."""
        from arena_buddy.db.personal_stats import compute_personal_augment_stats

        compute_personal_augment_stats(db_with_matches)

        rows = db_with_matches.execute(
            "SELECT * FROM personal_augment_stats ORDER BY augment_id"
        ).fetchall()
        assert len(rows) >= 1

    def test_augment_a_win_rate(self, db_with_matches: sqlite3.Connection) -> None:
        """Augment A (1001) appears in 2 games (both wins) => 100% win rate."""
        from arena_buddy.db.personal_stats import compute_personal_augment_stats

        compute_personal_augment_stats(db_with_matches)

        row = db_with_matches.execute(
            "SELECT * FROM personal_augment_stats WHERE champion_id = 236 AND augment_id = 1001"
        ).fetchone()
        assert row is not None
        assert row["games_played"] == 2
        assert row["wins"] == 2
        assert abs(row["win_rate"] - 1.0) < 0.01

    def test_augment_b_win_rate(self, db_with_matches: sqlite3.Connection) -> None:
        """Augment B (2001) appears in 2 games (1 win, 1 loss) => 50% win rate."""
        from arena_buddy.db.personal_stats import compute_personal_augment_stats

        compute_personal_augment_stats(db_with_matches)

        row = db_with_matches.execute(
            "SELECT * FROM personal_augment_stats WHERE champion_id = 236 AND augment_id = 2001"
        ).fetchone()
        assert row is not None
        assert row["games_played"] == 2
        assert row["wins"] == 1
        assert abs(row["win_rate"] - 0.5) < 0.01

    def test_augment_stats_idempotent(self, db_with_matches: sqlite3.Connection) -> None:
        """Running computation twice doesn't double counts."""
        from arena_buddy.db.personal_stats import compute_personal_augment_stats

        compute_personal_augment_stats(db_with_matches)
        compute_personal_augment_stats(db_with_matches)

        row = db_with_matches.execute(
            "SELECT * FROM personal_augment_stats WHERE champion_id = 236 AND augment_id = 1001"
        ).fetchone()
        assert row is not None
        assert row["games_played"] == 2  # not 4


# ---------------------------------------------------------------------------
# Recompute all tests
# ---------------------------------------------------------------------------

class TestRecomputeAll:
    """Tests for recompute_all()."""

    def test_recompute_all_runs_both(self, db_with_matches: sqlite3.Connection) -> None:
        """recompute_all() populates both stats tables."""
        from arena_buddy.db.personal_stats import recompute_all

        recompute_all(db_with_matches)

        item_rows = db_with_matches.execute(
            "SELECT COUNT(*) FROM personal_item_stats"
        ).fetchone()
        augment_rows = db_with_matches.execute(
            "SELECT COUNT(*) FROM personal_augment_stats"
        ).fetchone()
        assert item_rows[0] > 0
        assert augment_rows[0] > 0

    def test_recompute_all_idempotent(self, db_with_matches: sqlite3.Connection) -> None:
        """Running recompute_all twice doesn't double counts."""
        from arena_buddy.db.personal_stats import recompute_all

        recompute_all(db_with_matches)
        recompute_all(db_with_matches)

        item_count = db_with_matches.execute(
            "SELECT COUNT(*) FROM personal_item_stats"
        ).fetchone()[0]
        augment_count = db_with_matches.execute(
            "SELECT COUNT(*) FROM personal_augment_stats"
        ).fetchone()[0]
        # Counts should be the same as single run
        assert item_count == 3  # IE for Lucian (3 games), Quickblades (1 game), BORK (1 game)
        assert augment_count == 2  # AugA (1001) and AugB (2001)
