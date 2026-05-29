"""Tests for arena_buddy.db.aggregate_stats — Aggregate stats computation.

Tests written FIRST (RED phase) — these WILL fail until aggregate_stats.py exists.
"""

from __future__ import annotations

import sqlite3
from unittest import mock

import pytest

from arena_buddy.db.schema import create_all


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn_with_matches(temp_db_path):
    """Database with schema + match data for aggregate stats computation."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_all(conn)

    # Seed champions, items, augments needed for FK references
    conn.execute(
        "INSERT OR IGNORE INTO champions(id, key, name) VALUES (236, 'Lucian', 'Lucian')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO champions(id, key, name) VALUES (24, 'Jax', 'Jax')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO items(id, name, icon_filename) VALUES (3031, 'Infinity Edge', '3031.png')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO items(id, name, icon_filename) VALUES (6694, 'Quickblades', '6694.png')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO items(id, name, icon_filename) VALUES (3153, 'BORK', '3153.png')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO augments(id, api_name, name, rarity) VALUES (1001, 'AugA', 'Augment A', 0)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO augments(id, api_name, name, rarity) VALUES (2001, 'AugB', 'Augment B', 1)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO augments(id, api_name, name, rarity) VALUES (3001, 'AugC', 'Augment C', 2)"
    )

    # Insert 3 matches for Lucian: 2 wins (placement 1,1), 1 loss (placement 3)
    # Match 1: Win
    conn.execute(
        """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement, kills, deaths, assists)
           VALUES ('game_1', 236, 'Lucian', 'CHERRY', 1, 1, 8, 2, 5)"""
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

    # Match 2: Win
    conn.execute(
        """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement, kills, deaths, assists)
           VALUES ('game_2', 236, 'Lucian', 'CHERRY', 1, 1, 10, 1, 4)"""
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
        """INSERT INTO match_items(game_id, participant_id, item_id, slot)
           VALUES ('game_2', 2, 6694, 1)"""
    )
    conn.execute(
        """INSERT INTO match_augments(game_id, participant_id, augment_id, slot)
           VALUES ('game_2', 2, 1001, 0)"""
    )

    # Match 3: Loss
    conn.execute(
        """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement, kills, deaths, assists)
           VALUES ('game_3', 236, 'Lucian', 'CHERRY', 0, 3, 4, 6, 7)"""
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
    conn.execute(
        """INSERT INTO match_augments(game_id, participant_id, augment_id, slot)
           VALUES ('game_3', 3, 3001, 1)"""
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def empty_conn(temp_db_path):
    """Database with schema but no match data."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_all(conn)

    # Seed champions for FK
    conn.execute(
        "INSERT OR IGNORE INTO champions(id, key, name) VALUES (236, 'Lucian', 'Lucian')"
    )
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# compute_champion_stats tests
# ---------------------------------------------------------------------------

class TestComputeChampionStats:
    """Tests for compute_champion_stats()."""

    def test_compute_champion_stats_basic(self, conn_with_matches: sqlite3.Connection) -> None:
        """With seeded match data, verify structure of returned dict."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        assert "total_games" in stats
        assert "wins" in stats
        assert "losses" in stats
        assert "win_rate" in stats
        assert "avg_placement" in stats
        assert "placement_distribution" in stats
        assert "avg_kills" in stats
        assert "avg_deaths" in stats
        assert "avg_assists" in stats
        assert "avg_kda" in stats
        assert "top_items" in stats
        assert "top_augments" in stats

        assert stats["total_games"] == 3
        assert stats["wins"] == 2
        assert stats["losses"] == 1

    def test_compute_champion_stats_empty(self, empty_conn: sqlite3.Connection) -> None:
        """Returns zeros/defaults when no matches exist."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(empty_conn, 236)

        assert stats["total_games"] == 0
        assert stats["wins"] == 0
        assert stats["losses"] == 0
        assert stats["win_rate"] == 0.0
        assert stats["avg_placement"] == 0.0
        assert stats["placement_distribution"] == {1: 0, 2: 0, 3: 0, 4: 0}
        assert stats["avg_kills"] == 0.0
        assert stats["avg_deaths"] == 0.0
        assert stats["avg_assists"] == 0.0
        assert stats["avg_kda"] == 0.0
        assert stats["top_items"] == []
        assert stats["top_augments"] == []

    def test_compute_champion_stats_win_rate(self, conn_with_matches: sqlite3.Connection) -> None:
        """verify win_rate = wins / total_games."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        assert stats["total_games"] == 3
        assert stats["wins"] == 2
        assert stats["losses"] == 1
        assert stats["win_rate"] == pytest.approx(2 / 3)

    def test_compute_champion_stats_avg_placement(self, conn_with_matches: sqlite3.Connection) -> None:
        """verify avg placement calculation."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        # Placements: 1, 1, 3 → avg = 5/3 ≈ 1.667
        assert stats["avg_placement"] == pytest.approx(5 / 3)

    def test_compute_champion_stats_placement_distribution(self, conn_with_matches: sqlite3.Connection) -> None:
        """placement_distribution is a dict with counts per placement."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        assert stats["placement_distribution"] == {1: 2, 2: 0, 3: 1, 4: 0}

    def test_compute_champion_stats_kda(self, conn_with_matches: sqlite3.Connection) -> None:
        """avg_kills, avg_deaths, avg_assists, avg_kda are correct."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        # Game 1: 8/2/5, Game 2: 10/1/4, Game 3: 4/6/7
        # Avg kills: (8+10+4)/3 = 22/3 ≈ 7.333
        # Avg deaths: (2+1+6)/3 = 9/3 = 3.0
        # Avg assists: (5+4+7)/3 = 16/3 ≈ 5.333
        # KDA: (8+10+4) / (2+1+6) = 22/9 ≈ 2.444 (total kills / total deaths)
        assert stats["avg_kills"] == pytest.approx(22 / 3)
        assert stats["avg_deaths"] == pytest.approx(9 / 3)
        assert stats["avg_assists"] == pytest.approx(16 / 3)
        assert stats["avg_kda"] == pytest.approx(22 / 9)

    def test_compute_champion_stats_kda_zero_deaths(self, empty_conn: sqlite3.Connection) -> None:
        """When no matches, avg_kda is 0.0 (no division by zero)."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(empty_conn, 236)
        assert stats["avg_kda"] == 0.0

    def test_compute_champion_stats_top_items(self, conn_with_matches: sqlite3.Connection) -> None:
        """top_items returns most-used items with correct structure."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        assert isinstance(stats["top_items"], list)
        assert len(stats["top_items"]) >= 1
        # Infinity Edge (3031) appears in all 3 games
        ie_item = next((i for i in stats["top_items"] if i["item_id"] == 3031), None)
        assert ie_item is not None
        assert ie_item["item_name"] == "Infinity Edge"
        assert ie_item["games"] == 3
        assert ie_item["wins"] == 2
        assert ie_item["win_rate"] == pytest.approx(2 / 3)

    def test_compute_champion_stats_top_items_max_5(self, conn_with_matches: sqlite3.Connection) -> None:
        """top_items returns at most 5 items."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)
        assert len(stats["top_items"]) <= 5

    def test_compute_champion_stats_top_augments(self, conn_with_matches: sqlite3.Connection) -> None:
        """top_augments returns most-used augments with correct structure."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)

        assert isinstance(stats["top_augments"], list)
        assert len(stats["top_augments"]) >= 1
        # Augment A (1001) appears in 2 games, both wins
        aug_a = next((a for a in stats["top_augments"] if a["augment_id"] == 1001), None)
        assert aug_a is not None
        assert aug_a["augment_name"] == "Augment A"
        assert aug_a["rarity"] == 0
        assert aug_a["games"] == 2
        assert aug_a["wins"] == 2
        assert aug_a["win_rate"] == pytest.approx(1.0)

    def test_compute_champion_stats_top_augments_max_5(self, conn_with_matches: sqlite3.Connection) -> None:
        """top_augments returns at most 5 augments."""
        from arena_buddy.db.aggregate_stats import compute_champion_stats

        stats = compute_champion_stats(conn_with_matches, 236)
        assert len(stats["top_augments"]) <= 5


# ---------------------------------------------------------------------------
# compute_item_stats tests
# ---------------------------------------------------------------------------

class TestComputeItemStats:
    """Tests for compute_item_stats()."""

    def test_compute_item_stats(self, conn_with_matches: sqlite3.Connection) -> None:
        """Per-item stats for a specific item on a champion."""
        from arena_buddy.db.aggregate_stats import compute_item_stats

        stats = compute_item_stats(conn_with_matches, 236, 3031)

        assert stats["champion_id"] == 236
        assert stats["item_id"] == 3031
        assert stats["item_name"] == "Infinity Edge"
        assert stats["games"] == 3
        assert stats["wins"] == 2
        assert stats["win_rate"] == pytest.approx(2 / 3)

    def test_compute_item_stats_no_games(self, empty_conn: sqlite3.Connection) -> None:
        """Returns zeros when no matches with that item."""
        from arena_buddy.db.aggregate_stats import compute_item_stats

        stats = compute_item_stats(empty_conn, 236, 3031)

        assert stats["champion_id"] == 236
        assert stats["games"] == 0
        assert stats["wins"] == 0
        assert stats["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# compute_augment_stats tests
# ---------------------------------------------------------------------------

class TestComputeAugmentStats:
    """Tests for compute_augment_stats()."""

    def test_compute_augment_stats(self, conn_with_matches: sqlite3.Connection) -> None:
        """Per-augment stats for a specific augment on a champion."""
        from arena_buddy.db.aggregate_stats import compute_augment_stats

        stats = compute_augment_stats(conn_with_matches, 236, 1001)

        assert stats["champion_id"] == 236
        assert stats["augment_id"] == 1001
        assert stats["augment_name"] == "Augment A"
        assert stats["rarity"] == 0
        assert stats["games"] == 2
        assert stats["wins"] == 2
        assert stats["win_rate"] == pytest.approx(1.0)

    def test_compute_augment_stats_no_games(self, empty_conn: sqlite3.Connection) -> None:
        """Returns zeros when no matches with that augment."""
        from arena_buddy.db.aggregate_stats import compute_augment_stats

        stats = compute_augment_stats(empty_conn, 236, 1001)

        assert stats["champion_id"] == 236
        assert stats["games"] == 0
        assert stats["wins"] == 0
        assert stats["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# compute_all_champion_stats tests
# ---------------------------------------------------------------------------

class TestComputeAllChampionStats:
    """Tests for compute_all_champion_stats()."""

    def test_compute_all_champion_stats(self, conn_with_matches: sqlite3.Connection) -> None:
        """Returns list of stats for all champions the user has played."""
        # Add a Jax match too
        conn_with_matches.execute(
            """INSERT INTO matches(game_id, champion_id, champion_key, game_mode, win, placement, kills, deaths, assists)
               VALUES ('game_jax', 24, 'Jax', 'CHERRY', 0, 4, 2, 8, 1)"""
        )
        conn_with_matches.execute(
            """INSERT INTO match_participants(id, game_id, champion_id, champion_key, win)
               VALUES (4, 'game_jax', 24, 'Jax', 0)"""
        )
        conn_with_matches.commit()

        from arena_buddy.db.aggregate_stats import compute_all_champion_stats

        all_stats = compute_all_champion_stats(conn_with_matches)

        assert isinstance(all_stats, list)
        assert len(all_stats) == 2  # Lucian and Jax

        # Find Lucian
        lucian = next((s for s in all_stats if s.get("champion_id") == 236), None)
        assert lucian is not None
        assert lucian["total_games"] == 3

        # Find Jax
        jax = next((s for s in all_stats if s.get("champion_id") == 24), None)
        assert jax is not None
        assert jax["total_games"] == 1

    def test_compute_all_champion_stats_empty(self, empty_conn: sqlite3.Connection) -> None:
        """Returns empty list when no matches."""
        from arena_buddy.db.aggregate_stats import compute_all_champion_stats

        stats = compute_all_champion_stats(empty_conn)
        assert stats == []


# ---------------------------------------------------------------------------
# sync_riot_matches tests
# ---------------------------------------------------------------------------

class TestSyncRiotMatches:
    """Tests for sync_riot_matches()."""

    def test_sync_riot_matches_skips_existing(self, conn_with_matches: sqlite3.Connection) -> None:
        """Idempotent — does not duplicate existing matches."""
        from arena_buddy.db.aggregate_stats import sync_riot_matches

        # Create a mock Riot client that returns match IDs we already have
        mock_client = mock.MagicMock()
        # Mock async methods with AsyncMock so they can be awaited
        mock_client.get_match_history = mock.AsyncMock(return_value=["game_1", "game_2", "new_game_4"])
        mock_client.get_match_detail = mock.AsyncMock()

        # Only new_game_4 should result in a detail fetch
        mock_client.get_match_detail.return_value = {
            "metadata": {"matchId": "new_game_4"},
            "info": {
                "gameMode": "CHERRY",
                "queueId": 1700,
                "participants": [
                    {
                        "puuid": "test-puuid",
                        "championId": 236,
                        "championName": "Lucian",
                        "placement": 1,
                        "win": True,
                        "kills": 5,
                        "deaths": 3,
                        "assists": 8,
                        "items": [3031, 6694, 0, 0, 0, 0, 0],
                        "augments": ["AugA", "AugB"],
                    },
                    {
                        "puuid": "other-puuid",
                        "championId": 24,
                        "championName": "Jax",
                        "placement": 2,
                        "win": False,
                        "kills": 2,
                        "deaths": 4,
                        "assists": 2,
                        "items": [3031, 0, 0, 0, 0, 0, 0],
                        "augments": ["AugC"],
                    },
                ],
                "gameEndTimestamp": 1700000000000,
            },
        }

        result = sync_riot_matches(
            conn_with_matches,
            mock_client,
            "test-puuid",
            champion_id=236,
            count=5,
        )

        assert result["new_matches"] == 1
        # Only one detail call (for the new match)
        assert mock_client.get_match_detail.call_count == 1
        mock_client.get_match_detail.assert_called_with("new_game_4")

    def test_sync_riot_matches_new_match(self, conn_with_matches: sqlite3.Connection) -> None:
        """Stores a new match from Riot API."""
        from arena_buddy.db.aggregate_stats import sync_riot_matches

        mock_client = mock.MagicMock()
        mock_client.get_match_history = mock.AsyncMock(return_value=["new_game_5"])
        mock_client.get_match_detail = mock.AsyncMock()
        mock_client.get_match_detail.return_value = {
            "metadata": {"matchId": "new_game_5"},
            "info": {
                "gameMode": "CHERRY",
                "queueId": 1700,
                "participants": [
                    {
                        "puuid": "test-puuid",
                        "championId": 236,
                        "championName": "Lucian",
                        "placement": 1,
                        "win": True,
                        "kills": 7,
                        "deaths": 2,
                        "assists": 6,
                        "items": [3031, 6694, 3153, 0, 0, 0, 0],
                        "augments": ["AugA", "AugB"],
                    },
                    {
                        "puuid": "other-puuid",
                        "championId": 24,
                        "championName": "Jax",
                        "placement": 2,
                        "win": False,
                        "kills": 3,
                        "deaths": 5,
                        "assists": 1,
                        "items": [3153, 0, 0, 0, 0, 0, 0],
                        "augments": ["AugC"],
                    },
                ],
                "gameEndTimestamp": 1700000000000,
            },
        }

        result = sync_riot_matches(
            conn_with_matches,
            mock_client,
            "test-puuid",
            champion_id=236,
            count=5,
        )

        assert result["new_matches"] == 1
        # Verify the match was inserted
        match_row = conn_with_matches.execute(
            "SELECT * FROM matches WHERE game_id = 'new_game_5'"
        ).fetchone()
        assert match_row is not None
        assert match_row["champion_id"] == 236
        assert match_row["win"] == 1
        assert match_row["placement"] == 1

        # Verify participants were inserted
        participants = conn_with_matches.execute(
            "SELECT * FROM match_participants WHERE game_id = 'new_game_5'"
        ).fetchall()
        assert len(participants) == 2

        # Verify items were inserted for the player's participant
        items = conn_with_matches.execute(
            "SELECT mi.item_id FROM match_items mi "
            "JOIN match_participants mp ON mi.participant_id = mp.id "
            "WHERE mi.game_id = 'new_game_5' AND mp.puuid = 'test-puuid'"
        ).fetchall()
        item_ids = [i["item_id"] for i in items]
        assert 3031 in item_ids
        assert 6694 in item_ids
        assert 3153 in item_ids

        # Verify augments were inserted
        augments = conn_with_matches.execute(
            "SELECT ma.augment_id FROM match_augments ma "
            "JOIN match_participants mp ON ma.participant_id = mp.id "
            "WHERE ma.game_id = 'new_game_5' AND mp.puuid = 'test-puuid'"
        ).fetchall()
        augment_ids = [a["augment_id"] for a in augments]
        assert 1001 in augment_ids  # AugA
        assert 2001 in augment_ids  # AugB

    def test_sync_riot_matches_skips_non_arena(self, conn_with_matches: sqlite3.Connection) -> None:
        """Skips non-Arena matches (queue != 1700)."""
        from arena_buddy.db.aggregate_stats import sync_riot_matches

        mock_client = mock.MagicMock()
        mock_client.get_match_history = mock.AsyncMock(return_value=["summoners_rift_game"])
        mock_client.get_match_detail = mock.AsyncMock()
        mock_client.get_match_detail.return_value = {
            "metadata": {"matchId": "summoners_rift_game"},
            "info": {
                "gameMode": "CLASSIC",
                "queueId": 420,  # Not Arena
                "participants": [],
                "gameEndTimestamp": 1700000000000,
            },
        }

        result = sync_riot_matches(
            conn_with_matches,
            mock_client,
            "test-puuid",
            count=5,
        )

        assert result["new_matches"] == 0
