"""Tests for arena_buddy.db.queries — data access layer."""

import sqlite3

import pytest

from arena_buddy.db.schema import create_all


@pytest.fixture
def query_db(temp_db_path):
    """Database with schema and seed data, ready for query testing."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_all(conn)
    from arena_buddy.db.seed import seed_all
    seed_all(conn)
    yield conn
    conn.close()


class TestGetChampionByKey:
    """Tests for get_champion_by_key()."""

    def test_returns_lucian(self, query_db):
        """get_champion_by_key('Lucian') returns the champion row."""
        from arena_buddy.db.queries import get_champion_by_key

        champ = get_champion_by_key(query_db, "Lucian")
        assert champ is not None
        assert champ["key"] == "Lucian"
        assert champ["id"] == 236

    def test_returns_none_for_unknown(self, query_db):
        """Unknown champion returns None."""
        from arena_buddy.db.queries import get_champion_by_key

        champ = get_champion_by_key(query_db, "NoSuchChamp")
        assert champ is None

    def test_returns_all_fields(self, query_db):
        """Row includes id, key, name, icon_filename."""
        from arena_buddy.db.queries import get_champion_by_key

        champ = get_champion_by_key(query_db, "Lucian")
        assert "id" in champ.keys()
        assert "key" in champ.keys()
        assert "name" in champ.keys()
        assert "icon_filename" in champ.keys()


class TestGetItemsForChampion:
    """Tests for get_items_for_champion()."""

    def test_returns_items(self, query_db):
        """Returns a list of items with stats for the given champion."""
        from arena_buddy.db.queries import get_items_for_champion

        items = get_items_for_champion(query_db, champion_id=236, patch_id=1)
        assert len(items) >= 8
        assert items[0]["name"] is not None
        assert "win_rate" in items[0].keys()
        assert "pick_rate" in items[0].keys()

    def test_sorted_by_win_rate_desc(self, query_db):
        """Items are sorted by win_rate DESC (best first)."""
        from arena_buddy.db.queries import get_items_for_champion

        items = get_items_for_champion(query_db, champion_id=236, patch_id=1)
        win_rates = [item["win_rate"] for item in items]
        assert win_rates == sorted(win_rates, reverse=True)

    def test_returns_empty_for_unknown_champion(self, query_db):
        """Unknown champion returns empty list."""
        from arena_buddy.db.queries import get_items_for_champion

        items = get_items_for_champion(query_db, champion_id=9999, patch_id=1)
        assert items == []

    def test_includes_item_id_and_rank(self, query_db):
        """Each item dict includes id and rank fields."""
        from arena_buddy.db.queries import get_items_for_champion

        items = get_items_for_champion(query_db, champion_id=236, patch_id=1)
        for item in items:
            assert "id" in item
            assert "rank" in item

    def test_personal_stats_are_null_when_no_history(self, query_db):
        """When no personal match history exists, personal_win_rate is None."""
        from arena_buddy.db.queries import get_items_for_champion

        items = get_items_for_champion(query_db, champion_id=236, patch_id=1)
        for item in items:
            assert item["personal_win_rate"] is None
            assert item["personal_games"] == 0


class TestGetAugmentsForChampion:
    """Tests for get_augments_for_champion()."""

    def test_returns_augments_grouped(self, query_db):
        """Returns augments grouped by rarity tier."""
        from arena_buddy.db.queries import get_augments_for_champion

        result = get_augments_for_champion(query_db, champion_id=236, patch_id=1)
        assert "prismatic" in result
        assert "gold" in result
        assert "silver" in result

    def test_prismatic_sorted_by_win_rate(self, query_db):
        """Prismatic augments sorted by win_rate DESC."""
        from arena_buddy.db.queries import get_augments_for_champion

        result = get_augments_for_champion(query_db, champion_id=236, patch_id=1)
        prismatic = result["prismatic"]
        assert len(prismatic) == 3
        win_rates = [a["win_rate"] for a in prismatic]
        assert win_rates == sorted(win_rates, reverse=True)

    def test_gold_has_four_augments(self, query_db):
        """Gold tier has 4 augments from seed data."""
        from arena_buddy.db.queries import get_augments_for_champion

        result = get_augments_for_champion(query_db, champion_id=236, patch_id=1)
        assert len(result["gold"]) == 4

    def test_silver_has_three_augments(self, query_db):
        """Silver tier has 3 augments from seed data."""
        from arena_buddy.db.queries import get_augments_for_champion

        result = get_augments_for_champion(query_db, champion_id=236, patch_id=1)
        assert len(result["silver"]) == 3

    def test_augment_has_rarity_field(self, query_db):
        """Each augment includes a rarity integer."""
        from arena_buddy.db.queries import get_augments_for_champion

        result = get_augments_for_champion(query_db, champion_id=236, patch_id=1)
        for aug in result["prismatic"]:
            assert aug["rarity"] == 2
        for aug in result["gold"]:
            assert aug["rarity"] == 1
        for aug in result["silver"]:
            assert aug["rarity"] == 0


class TestGetCurrentPatch:
    """Tests for get_current_patch()."""

    def test_returns_current_patch(self, query_db):
        """Returns the patch marked as current."""
        from arena_buddy.db.queries import get_current_patch

        patch = get_current_patch(query_db)
        assert patch is not None
        assert patch["is_current"] == 1
        assert "version" in patch

    def test_returns_none_when_no_current(self, temp_db_path):
        """Returns None when no patch is marked current."""
        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        create_all(conn)

        from arena_buddy.db.queries import get_current_patch

        patch = get_current_patch(conn)
        assert patch is None
        conn.close()


class TestGetAllChampions:
    """Tests for get_all_champions()."""

    def test_returns_all_champions(self, query_db):
        """Returns all champions (172 when full dataset loaded)."""
        from arena_buddy.db.queries import get_all_champions

        champs = get_all_champions(query_db)
        assert len(champs) >= 1  # At least one
        assert any(c["key"] == "Lucian" for c in champs)

    def test_empty_when_no_champions(self, temp_db_path):
        """Empty list when no champions in DB."""
        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        create_all(conn)

        from arena_buddy.db.queries import get_all_champions

        champs = get_all_champions(conn)
        assert champs == []
        conn.close()
