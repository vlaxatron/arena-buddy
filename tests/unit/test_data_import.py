"""Tests for arena_buddy.db.importer — data import from DDragon / CDragon JSON."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from arena_buddy.db.importer import (
    import_all,
    import_augments,
    import_champions,
    import_items,
)
from arena_buddy.db.schema import create_all


# ---------------------------------------------------------------------------
# Test helpers — build small in-memory JSON fixtures
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj: object) -> None:
    """Write *obj* as JSON to *path*."""
    path.write_text(json.dumps(obj), encoding="utf-8")


# ---------------------------------------------------------------------------
# Champions fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def champions_json_path(tmp_path: Path) -> Path:
    """A small Data Dragon champions JSON with 4 entries."""
    data = {
        "type": "champion",
        "format": "standAloneComplex",
        "version": "16.11.1",
        "data": {
            "Aatrox": {
                "id": "Aatrox",
                "key": "266",
                "name": "Aatrox",
                "image": {"full": "Aatrox.png"},
            },
            "Ahri": {
                "id": "Ahri",
                "key": "103",
                "name": "Ahri",
                "image": {"full": "Ahri.png"},
            },
            "Lucian": {
                "id": "Lucian",
                "key": "236",
                "name": "Lucian",
                "image": {"full": "Lucian.png"},
            },
            "Zed": {
                "id": "Zed",
                "key": "238",
                "name": "Zed",
                "image": {"full": "Zed.png"},
            },
        },
    }
    path = tmp_path / "champions.json"
    _write_json(path, data)
    return path


# ---------------------------------------------------------------------------
# Items fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def items_json_path(tmp_path: Path) -> Path:
    """A small Data Dragon items JSON with 5 entries."""
    data = {
        "type": "item",
        "version": "16.11.1",
        "data": {
            "1001": {
                "name": "Boots",
                "gold": {"total": 300},
                "image": {"full": "1001.png"},
                "plaintext": "Slightly increases Move Speed",
            },
            "2003": {
                "name": "Health Potion",
                "gold": {"total": 50},
                "image": {"full": "2003.png"},
                "plaintext": "Regenerates health",
            },
            "3078": {
                "name": "Trinity Force",
                "gold": {"total": 3333},
                "image": {"full": "3078.png"},
                "description": "Tons of damage",
            },
            "6672": {
                "name": "Kraken Slayer",
                "gold": {"total": 3100},
                "image": {"full": "6672.png"},
                "plaintext": "Every third attack deals bonus magic damage.",
            },
            "3031": {
                "name": "Infinity Edge",
                "gold": {"total": 3400},
                "image": {"full": "3031.png"},
                "plaintext": "Critical strikes deal bonus damage.",
            },
        },
    }
    path = tmp_path / "items.json"
    _write_json(path, data)
    return path


# ---------------------------------------------------------------------------
# Augments fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def augments_json_path(tmp_path: Path) -> Path:
    """A small CommunityDragon augments JSON with 4 entries."""
    data = {
        "augments": [
            {
                "apiName": "WarmupRoutine",
                "name": "Warmup Routine",
                "rarity": 0,
                "desc": "Gain increasing damage over time.",
                "iconSmall": "assets/ux/cherry/augments/icons/warmuproutine_small.png",
            },
            {
                "apiName": "BackToBasics",
                "name": "Back To Basics",
                "rarity": 2,
                "desc": "Basic abilities deal massively increased damage.",
                "iconSmall": "assets/ux/cherry/augments/icons/backtobasics_small.png",
            },
            {
                "apiName": "ADAPt",
                "name": "ADAPt",
                "rarity": 1,
                "desc": "Gain adaptive force based on items.",
                "iconSmall": "assets/ux/cherry/augments/icons/adapt_small.png",
            },
            {
                "apiName": "SymphonyOfWar",
                "name": "Symphony of War",
                "rarity": 2,
                "desc": "Gain massive attack speed and on-hit damage.",
                "iconSmall": "assets/ux/cherry/augments/icons/symphonyofwar_small.png",
            },
        ],
    }
    path = tmp_path / "augments.json"
    _write_json(path, data)
    return path


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_db(temp_db_path: Path) -> sqlite3.Connection:
    """Return an open connection with the full schema created."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.row_factory = sqlite3.Row
    create_all(conn)
    return conn


# ===================================================================
# import_champions
# ===================================================================

class TestImportChampions:
    """Tests for :func:`import_champions`."""

    def test_inserts_all_champions(
        self, fresh_db: sqlite3.Connection, champions_json_path: Path
    ) -> None:
        """All 4 test champions are inserted."""
        count = import_champions(fresh_db, champions_json_path)
        assert count == 4

        rows = fresh_db.execute("SELECT id, key, name FROM champions ORDER BY id").fetchall()
        assert len(rows) == 4
        assert rows[0]["key"] == "Ahri"
        assert rows[0]["id"] == 103
        # Sorted by id: 103 Ahri, 236 Lucian, 238 Zed, 266 Aatrox
        assert rows[2]["key"] == "Zed"
        assert rows[2]["id"] == 238
        assert rows[3]["key"] == "Aatrox"
        assert rows[3]["id"] == 266

    def test_icon_filenames(
        self, fresh_db: sqlite3.Connection, champions_json_path: Path
    ) -> None:
        """Champion icon filenames are stored correctly."""
        import_champions(fresh_db, champions_json_path)
        row = fresh_db.execute(
            "SELECT icon_filename FROM champions WHERE key = 'Aatrox'"
        ).fetchone()
        assert row is not None
        assert row["icon_filename"] == "Aatrox.png"

    def test_idempotent(
        self, fresh_db: sqlite3.Connection, champions_json_path: Path
    ) -> None:
        """Running import_champions twice does not duplicate rows."""
        import_champions(fresh_db, champions_json_path)
        import_champions(fresh_db, champions_json_path)

        count = fresh_db.execute("SELECT COUNT(*) FROM champions").fetchone()[0]
        assert count == 4

    def test_file_not_found(self, fresh_db: sqlite3.Connection) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            import_champions(fresh_db, "/nonexistent/champions.json")

    def test_malformed_json(
        self, fresh_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Malformed JSON raises ValueError."""
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{{", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed JSON"):
            import_champions(fresh_db, bad)

    def test_missing_data_key(
        self, fresh_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """JSON without a 'data' key raises ValueError."""
        bad = tmp_path / "no_data.json"
        _write_json(bad, {"type": "champion"})
        with pytest.raises(ValueError, match="missing 'data' key"):
            import_champions(fresh_db, bad)


# ===================================================================
# import_items
# ===================================================================

class TestImportItems:
    """Tests for :func:`import_items`."""

    def test_inserts_all_items(
        self, fresh_db: sqlite3.Connection, items_json_path: Path
    ) -> None:
        """All 5 test items are inserted."""
        count = import_items(fresh_db, items_json_path)
        assert count == 5

        rows = fresh_db.execute("SELECT id, name, gold_cost FROM items ORDER BY id").fetchall()
        assert len(rows) == 5
        assert rows[0]["id"] == 1001
        assert rows[0]["name"] == "Boots"
        assert rows[0]["gold_cost"] == 300

    def test_item_description(
        self, fresh_db: sqlite3.Connection, items_json_path: Path
    ) -> None:
        """Item descriptions are stored (plaintext preferred)."""
        import_items(fresh_db, items_json_path)
        # Trinity Force uses "description" (no plaintext)
        row = fresh_db.execute(
            "SELECT description FROM items WHERE id = 3078"
        ).fetchone()
        assert row is not None
        assert "Tons of damage" in row["description"]

        # Boots uses plaintext
        row = fresh_db.execute(
            "SELECT description FROM items WHERE id = 1001"
        ).fetchone()
        assert "Slightly increases Move Speed" in row["description"]

    def test_idempotent(
        self, fresh_db: sqlite3.Connection, items_json_path: Path
    ) -> None:
        """Running import_items twice does not duplicate rows."""
        import_items(fresh_db, items_json_path)
        import_items(fresh_db, items_json_path)

        count = fresh_db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        assert count == 5

    def test_file_not_found(self, fresh_db: sqlite3.Connection) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            import_items(fresh_db, "/nonexistent/items.json")

    def test_malformed_json(
        self, fresh_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Malformed JSON raises ValueError."""
        bad = tmp_path / "bad.json"
        bad.write_text("}}}}", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed JSON"):
            import_items(fresh_db, bad)

    def test_missing_data_key(
        self, fresh_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """JSON without a 'data' key raises ValueError."""
        bad = tmp_path / "no_data.json"
        _write_json(bad, {"type": "item"})
        with pytest.raises(ValueError, match="missing 'data' key"):
            import_items(fresh_db, bad)


# ===================================================================
# import_augments
# ===================================================================

class TestImportAugments:
    """Tests for :func:`import_augments`."""

    def test_inserts_all_augments(
        self, fresh_db: sqlite3.Connection, augments_json_path: Path
    ) -> None:
        """All 4 test augments are inserted."""
        count = import_augments(fresh_db, augments_json_path)
        assert count == 4

        rows = fresh_db.execute(
            "SELECT id, api_name, name, rarity FROM augments ORDER BY id"
        ).fetchall()
        assert len(rows) == 4

    def test_ids_start_at_1000(
        self, fresh_db: sqlite3.Connection, augments_json_path: Path
    ) -> None:
        """Augment IDs begin at 1000 and increment."""
        import_augments(fresh_db, augments_json_path)
        min_id = fresh_db.execute(
            "SELECT MIN(id) FROM augments"
        ).fetchone()[0]
        assert min_id == 1000

    def test_ids_are_deterministic(
        self, fresh_db: sqlite3.Connection, augments_json_path: Path, temp_db_path: Path
    ) -> None:
        """Same JSON produces the same IDs (sorted by apiName)."""
        # First database
        import_augments(fresh_db, augments_json_path)
        first_run = fresh_db.execute(
            "SELECT api_name, id FROM augments ORDER BY id"
        ).fetchall()

        # Second, independent database — verify IDs match
        conn2 = sqlite3.connect(str(temp_db_path).replace(".db", "_2.db"))
        conn2.row_factory = sqlite3.Row
        create_all(conn2)
        try:
            import_augments(conn2, augments_json_path)
            second_run = conn2.execute(
                "SELECT api_name, id FROM augments ORDER BY id"
            ).fetchall()
        finally:
            conn2.close()

        assert first_run == second_run

    def test_icon_filenames_extracted(
        self, fresh_db: sqlite3.Connection, augments_json_path: Path
    ) -> None:
        """Augment icon_filename is the basename of iconSmall."""
        import_augments(fresh_db, augments_json_path)
        row = fresh_db.execute(
            "SELECT icon_filename FROM augments WHERE api_name = 'WarmupRoutine'"
        ).fetchone()
        assert row is not None
        assert row["icon_filename"] == "warmuproutine_small.png"

    def test_rarity_values(
        self, fresh_db: sqlite3.Connection, augments_json_path: Path
    ) -> None:
        """Rarity values are stored correctly."""
        import_augments(fresh_db, augments_json_path)

        prism = fresh_db.execute(
            "SELECT COUNT(*) FROM augments WHERE rarity = 2"
        ).fetchone()[0]
        assert prism == 2  # BackToBasics, SymphonyOfWar

        gold = fresh_db.execute(
            "SELECT COUNT(*) FROM augments WHERE rarity = 1"
        ).fetchone()[0]
        assert gold == 1  # ADAPt

        silver = fresh_db.execute(
            "SELECT COUNT(*) FROM augments WHERE rarity = 0"
        ).fetchone()[0]
        assert silver == 1  # WarmupRoutine

    def test_idempotent(
        self, fresh_db: sqlite3.Connection, augments_json_path: Path
    ) -> None:
        """Running import_augments twice does not duplicate rows."""
        import_augments(fresh_db, augments_json_path)
        import_augments(fresh_db, augments_json_path)

        count = fresh_db.execute("SELECT COUNT(*) FROM augments").fetchone()[0]
        assert count == 4

    def test_file_not_found(self, fresh_db: sqlite3.Connection) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            import_augments(fresh_db, "/nonexistent/augments.json")

    def test_malformed_json(
        self, fresh_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Malformed JSON raises ValueError."""
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed JSON"):
            import_augments(fresh_db, bad)

    def test_missing_augments_key(
        self, fresh_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """JSON without an 'augments' key raises ValueError."""
        bad = tmp_path / "no_augments.json"
        _write_json(bad, {"version": "1"})
        with pytest.raises(ValueError, match="missing 'augments' key"):
            import_augments(fresh_db, bad)


# ===================================================================
# import_all
# ===================================================================

class TestImportAll:
    """Tests for :func:`import_all`."""

    def test_import_all_returns_counts(
        self,
        fresh_db: sqlite3.Connection,
        champions_json_path: Path,
        items_json_path: Path,
        augments_json_path: Path,
    ) -> None:
        """import_all returns correct attempted counts."""
        result = import_all(
            fresh_db, champions_json_path, items_json_path, augments_json_path
        )
        assert result == {"champions": 4, "items": 5, "augments": 4}

    def test_import_all_populates_all_tables(
        self,
        fresh_db: sqlite3.Connection,
        champions_json_path: Path,
        items_json_path: Path,
        augments_json_path: Path,
    ) -> None:
        """All three tables have data after import_all."""
        import_all(fresh_db, champions_json_path, items_json_path, augments_json_path)

        assert fresh_db.execute("SELECT COUNT(*) FROM champions").fetchone()[0] == 4
        assert fresh_db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 5
        assert fresh_db.execute("SELECT COUNT(*) FROM augments").fetchone()[0] == 4

    def test_import_all_idempotent(
        self,
        fresh_db: sqlite3.Connection,
        champions_json_path: Path,
        items_json_path: Path,
        augments_json_path: Path,
    ) -> None:
        """Running import_all twice does not duplicate data."""
        import_all(fresh_db, champions_json_path, items_json_path, augments_json_path)
        import_all(fresh_db, champions_json_path, items_json_path, augments_json_path)

        assert fresh_db.execute("SELECT COUNT(*) FROM champions").fetchone()[0] == 4
        assert fresh_db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 5
        assert fresh_db.execute("SELECT COUNT(*) FROM augments").fetchone()[0] == 4

    def test_import_all_propagates_errors(
        self,
        fresh_db: sqlite3.Connection,
        items_json_path: Path,
        augments_json_path: Path,
    ) -> None:
        """If one path is bad, import_all propagates the error."""
        with pytest.raises(FileNotFoundError, match="not found"):
            import_all(
                fresh_db, "/bad/champions.json", items_json_path, augments_json_path
            )
