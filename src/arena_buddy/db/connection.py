"""Database connection management for Arena Buddy."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from arena_buddy.config import get_db_path
from arena_buddy.db.schema import create_all


@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding an open SQLite connection.

    Creates the database file and schema if they do not exist.

    Args:
        db_path: Optional explicit path.  Defaults to ``get_db_path()``.

    Yields:
        An open :class:`sqlite3.Connection` with foreign keys enabled.
    """
    path = str(db_path or get_db_path())
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    create_all(conn)
    try:
        yield conn
    finally:
        conn.close()


def init_database(db_path: Path | None = None) -> Path:
    """Ensure the database file and schema exist.

    Args:
        db_path: Optional explicit path.

    Returns:
        The Path to the database file.
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        create_all(conn)
    finally:
        conn.close()
    return path
