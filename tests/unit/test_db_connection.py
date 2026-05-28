"""Tests for arena_buddy.db.connection."""

import sqlite3

import pytest


class TestGetConnection:
    """Context manager tests."""

    def test_returns_connection(self):
        """get_connection yields a sqlite3.Connection."""
        from arena_buddy.db.connection import get_connection

        with get_connection() as conn:
            assert isinstance(conn, sqlite3.Connection)

    def test_foreign_keys_enabled(self):
        """Connection has foreign_keys pragma ON."""
        from arena_buddy.db.connection import get_connection

        with get_connection() as conn:
            result = conn.execute("PRAGMA foreign_keys").fetchone()
            assert result[0] == 1

    def test_connection_closes_after_context(self, temp_db_path):
        """Connection is closed after exiting the context manager."""
        from arena_buddy.db.connection import get_connection

        conn_ref = None
        with get_connection(temp_db_path) as conn:
            conn_ref = conn

        # After context exit, operations should raise or fail
        with pytest.raises(sqlite3.ProgrammingError):
            conn_ref.execute("SELECT 1")

    def test_creates_schema_on_connect(self, temp_db_path):
        """Tables are created automatically when connecting."""
        from arena_buddy.db.connection import get_connection

        with get_connection(temp_db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        table_names = {row[0] for row in tables}
        assert "champions" in table_names
        assert "items" in table_names
        assert "augments" in table_names

    def test_explicit_path_overrides_default(self, temp_db_path):
        """Explicit db_path is used instead of default."""
        from arena_buddy.db.connection import get_connection

        with get_connection(temp_db_path) as conn:
            pass
        # File should exist at the custom path
        assert temp_db_path.exists()

    def test_idempotent_reconnect(self, temp_db_path):
        """Connecting twice to the same path is safe."""
        from arena_buddy.db.connection import get_connection

        with get_connection(temp_db_path):
            pass
        with get_connection(temp_db_path):
            pass  # No error


class TestInitDatabase:
    """init_database tests."""

    def test_creates_db_file(self, tmp_path):
        """init_database creates the file if missing."""
        from arena_buddy.db.connection import init_database

        db_path = tmp_path / "test_create.db"
        assert not db_path.exists()
        result = init_database(db_path)
        assert result == db_path
        assert db_path.exists()

    def test_initializes_schema(self, temp_db_path):
        """Schema tables exist after init."""
        from arena_buddy.db.connection import init_database

        init_database(temp_db_path)
        conn = sqlite3.connect(str(temp_db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        conn.close()
        assert len(tables) == 6

    def test_returns_path(self):
        """Returns the Path to the database."""
        from arena_buddy.db.connection import init_database

        result = init_database()
        assert result.name == "arena_buddy.db"
