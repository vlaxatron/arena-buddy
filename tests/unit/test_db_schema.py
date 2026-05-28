"""Tests for arena_buddy.db.schema — SQLite table creation."""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(temp_db_path):
    """Return a connection to an empty temporary database."""
    conn = sqlite3.connect(str(temp_db_path))
    yield conn
    conn.close()


class TestCreateSchema:
    """Verify schema.create_all() creates all expected tables."""

    def test_creates_champions_table(self, fresh_db):
        """champions table exists with correct columns."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        cursor = fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='champions'")
        assert cursor.fetchone() is not None

    def test_creates_items_table(self, fresh_db):
        """items table exists."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        cursor = fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
        assert cursor.fetchone() is not None

    def test_creates_augments_table(self, fresh_db):
        """augments table exists."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        cursor = fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='augments'")
        assert cursor.fetchone() is not None

    def test_creates_patches_table(self, fresh_db):
        """patches table exists."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        cursor = fresh_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patches'")
        assert cursor.fetchone() is not None

    def test_creates_global_item_stats_table(self, fresh_db):
        """global_item_stats table exists."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='global_item_stats'"
        )
        assert cursor.fetchone() is not None

    def test_creates_global_augment_stats_table(self, fresh_db):
        """global_augment_stats table exists."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        cursor = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='global_augment_stats'"
        )
        assert cursor.fetchone() is not None

    def test_creates_all_tables_in_one_call(self, fresh_db):
        """All Phase 1 + Phase 2 tables are created (excluding internal sqlite_* tables)."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)

        tables = fresh_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        table_names = {row[0] for row in tables}
        expected = {
            "champions", "items", "augments", "patches",
            "global_item_stats", "global_augment_stats",
            # Phase 2 tables
            "matches", "match_participants", "match_items", "match_augments",
            "personal_item_stats", "personal_augment_stats",
        }
        assert table_names == expected

    def test_is_idempotent(self, fresh_db):
        """Running create_all twice should not error."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)
        create_all(fresh_db)  # Should not raise

    def test_champions_has_correct_columns(self, fresh_db):
        """champions table has the expected column names."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)
        columns = fresh_db.execute("PRAGMA table_info(champions)").fetchall()
        col_names = {col[1] for col in columns}
        assert col_names == {"id", "key", "name", "icon_filename"}

    def test_items_has_correct_columns(self, fresh_db):
        """items table has expected columns."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)
        columns = fresh_db.execute("PRAGMA table_info(items)").fetchall()
        col_names = {col[1] for col in columns}
        assert col_names == {"id", "name", "icon_filename", "gold_cost", "description"}

    def test_augments_has_correct_columns(self, fresh_db):
        """augments table has expected columns."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)
        columns = fresh_db.execute("PRAGMA table_info(augments)").fetchall()
        col_names = {col[1] for col in columns}
        assert col_names == {"id", "api_name", "name", "rarity", "description", "icon_filename"}

    def test_patches_has_correct_columns(self, fresh_db):
        """patches table has expected columns."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)
        columns = fresh_db.execute("PRAGMA table_info(patches)").fetchall()
        col_names = {col[1] for col in columns}
        assert col_names == {"id", "version", "scraped_at", "is_current"}

    def test_global_item_stats_has_composite_pk(self, fresh_db):
        """global_item_stats has composite PRIMARY KEY (champion_id, item_id, patch_id)."""
        from arena_buddy.db.schema import create_all

        create_all(fresh_db)
        # Verify the composite PK by inserting duplicate and expecting IntegrityError
        fresh_db.execute(
            "INSERT INTO champions(id, key, name) VALUES (1, 'Test', 'Test')"
        )
        fresh_db.execute(
            "INSERT INTO items(id, name) VALUES (100, 'TestItem')"
        )
        fresh_db.execute(
            "INSERT INTO patches(version, is_current) VALUES ('99.99', 1)"
        )
        fresh_db.execute(
            "INSERT INTO global_item_stats(champion_id, item_id, patch_id, win_rate) "
            "VALUES (1, 100, 1, 0.5)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO global_item_stats(champion_id, item_id, patch_id, win_rate) "
                "VALUES (1, 100, 1, 0.6)"
            )
