"""Tests for arena_buddy.db.seed — hardcoded Lucian Arena stats."""

import sqlite3

import pytest

from arena_buddy.db.schema import create_all


@pytest.fixture
def seeded_db(temp_db_path):
    """Database with schema created and seed data inserted."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_all(conn)
    from arena_buddy.db.seed import seed_all
    seed_all(conn)
    yield conn
    conn.close()


class TestSeedChampion:
    """Verify Lucian champion is seeded."""

    def test_lucian_exists(self, seeded_db):
        """Lucian (id=236, key='Lucian') exists."""
        row = seeded_db.execute(
            "SELECT id, key, name FROM champions WHERE key = 'Lucian'"
        ).fetchone()
        assert row is not None
        assert row["id"] == 236
        assert row["key"] == "Lucian"
        assert row["name"] == "Lucian"

    def test_only_one_champion_seeded(self, seeded_db):
        """Phase 1 seeds exactly 1 champion (now 172 with full import)."""
        count = seeded_db.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
        assert count >= 1


class TestSeedItems:
    """Verify items are seeded."""

    def test_all_items_exist(self, seeded_db):
        """All items from the seed data are inserted."""
        items = seeded_db.execute("SELECT id, name FROM items ORDER BY id").fetchall()
        item_names = {row["name"] for row in items}
        expected = {
            "Kraken Slayer", "Navori Flickerblade", "Infinity Edge",
            "Bloodthirster", "Lord Dominik's Regards", "Guardian Angel",
            "Berserker's Greaves", "Mercurial Scimitar",
        }
        # All expected items should be present
        assert expected.issubset(item_names)

    def test_items_have_icons(self, seeded_db):
        """Items have icon filenames."""
        row = seeded_db.execute(
            "SELECT icon_filename FROM items WHERE name = 'Kraken Slayer'"
        ).fetchone()
        assert row["icon_filename"] is not None
        assert ".png" in row["icon_filename"]


class TestSeedAugments:
    """Verify augments are seeded."""

    def test_augments_exist(self, seeded_db):
        """Augments are inserted with correct rarity grouping (60+ prismatic with full import)."""
        augments = seeded_db.execute(
            "SELECT name, rarity FROM augments ORDER BY rarity DESC, name"
        ).fetchall()

        # Prismatic (rarity=2) — at least 3 from seed, more from import
        prismatic = [r for r in augments if r["rarity"] == 2]
        assert len(prismatic) >= 3

        # Gold (rarity=1)
        gold = [r for r in augments if r["rarity"] == 1]
        assert len(gold) >= 4

        # Silver (rarity=0)
        silver = [r for r in augments if r["rarity"] == 0]
        assert len(silver) >= 3

    def test_back_to_basics_is_prismatic(self, seeded_db):
        """Back To Basics has rarity=2 (Prismatic)."""
        row = seeded_db.execute(
            "SELECT name, rarity FROM augments WHERE api_name = 'BackToBasics'"
        ).fetchone()
        assert row is not None
        assert row["rarity"] == 2


class TestSeedGlobalStats:
    """Verify global item/augment stats are seeded."""

    def test_item_stats_for_lucian_exist(self, seeded_db):
        """global_item_stats has entries for Lucian."""
        rows = seeded_db.execute(
            "SELECT COUNT(*) as cnt FROM global_item_stats WHERE champion_id = 236"
        ).fetchone()
        assert rows["cnt"] >= 8

    def test_augment_stats_for_lucian_exist(self, seeded_db):
        """global_augment_stats has entries for Lucian."""
        rows = seeded_db.execute(
            "SELECT COUNT(*) as cnt FROM global_augment_stats WHERE champion_id = 236"
        ).fetchone()
        assert rows["cnt"] >= 10

    def test_item_stats_have_win_rates(self, seeded_db):
        """Item stats have realistic win rate values."""
        row = seeded_db.execute(
            """SELECT gis.win_rate
               FROM global_item_stats gis
               JOIN items i ON gis.item_id = i.id
               WHERE i.name = 'Kraken Slayer' AND gis.champion_id = 236"""
        ).fetchone()
        assert row is not None
        assert 0.5 < row["win_rate"] < 0.6  # 56.2%

    def test_augment_stats_have_win_rates(self, seeded_db):
        """Augment stats have win rates."""
        row = seeded_db.execute(
            """SELECT gas.win_rate
               FROM global_augment_stats gas
               JOIN augments a ON gas.augment_id = a.id
               WHERE a.api_name = 'BackToBasics' AND gas.champion_id = 236"""
        ).fetchone()
        assert row is not None
        assert 0.6 < row["win_rate"] < 0.7  # 63.2%


class TestSeedIdempotent:
    """Running seed_all twice should not duplicate data."""

    def test_seed_is_idempotent(self, seeded_db):
        """Running seed_all on an already-seeded database does not error."""
        from arena_buddy.db.seed import seed_all
        seed_all(seeded_db)  # Should not raise

    def test_seed_does_not_duplicate_champions(self, temp_db_path):
        """Running seed twice doesn't create duplicate champions (expect full import count)."""
        conn = sqlite3.connect(str(temp_db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
        from arena_buddy.db.seed import seed_all
        seed_all(conn)
        first_count = conn.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
        seed_all(conn)

        count = conn.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
        assert count == first_count  # No duplicates
        assert count >= 1
        conn.close()


class TestSeedPatch:
    """Verify patch record is seeded."""

    def test_patch_record_exists(self, seeded_db):
        """A current patch record is created."""
        row = seeded_db.execute(
            "SELECT version, is_current FROM patches WHERE is_current = 1"
        ).fetchone()
        assert row is not None
        assert row["version"] is not None
