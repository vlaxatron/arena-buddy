"""Conftest for arena_buddy tests."""

import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_db_path():
    """Temporary database path for tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def temp_cache_dir():
    """Temporary cache directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_config_dir():
    """Temporary config directory for tests."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
