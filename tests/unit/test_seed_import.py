"""Tests for seed data auto-import from Data Dragon files.

Ensures the full 172-champion dataset downloads and imports correctly
on first run, not just the 6 hardcoded champions.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Test: _seed_from_files imports champions+items even without augments.json
# ---------------------------------------------------------------------------

class TestSeedFromFilesImport:
    """The seed importer should import champions and items from cache
    files even when augments.json is missing."""

    def test_imports_without_augments_file(self):
        """Champions and items should import when augments.json is absent."""
        from arena_buddy.db.seed import _seed_from_files, _CACHE_DIR
        from arena_buddy.db.importer import import_champions, import_items
        from arena_buddy.db.schema import create_all

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            # Create a fake champions.json
            champ_data = {
                "data": {
                    "Aatrox": {
                        "key": "266", "name": "Aatrox",
                        "id": "Aatrox", "image": {"full": "Aatrox.png"}
                    },
                    "Ahri": {
                        "key": "103", "name": "Ahri",
                        "id": "Ahri", "image": {"full": "Ahri.png"}
                    },
                    "Zed": {
                        "key": "238", "name": "Zed",
                        "id": "Zed", "image": {"full": "Zed.png"}
                    },
                }
            }
            (cache / "champions.json").write_text(json.dumps(champ_data))

            # Create a fake items.json
            item_data = {
                "data": {
                    "1001": {
                        "name": "Boots", "image": {"full": "1001.png"},
                        "gold": {"total": 300}, "plaintext": "Basic boots"
                    },
                    "3078": {
                        "name": "Trinity Force", "image": {"full": "3078.png"},
                        "gold": {"total": 3333}, "plaintext": "Tons of damage"
                    },
                }
            }
            (cache / "items.json").write_text(json.dumps(item_data))

            # NO augments.json — we want the import to still work

            # Create a temp DB
            db = sqlite3.connect(Path(tmp) / "test.db")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            create_all(db)

            # Patch _CACHE_DIR to point to our temp dir
            with patch("arena_buddy.db.seed._CACHE_DIR", cache):
                _seed_from_files(db)

            # Verify champions were imported
            champions = db.execute(
                "SELECT id, key, name FROM champions ORDER BY name"
            ).fetchall()
            champ_dicts = [dict(r) for r in champions]
            assert len(champ_dicts) >= 3, f"Expected ≥3 champions, got {len(champ_dicts)}"
            ahri = [c for c in champ_dicts if c["key"] == "Ahri"]
            assert len(ahri) == 1, "Ahri should be imported"

            # Verify items were imported
            items = db.execute(
                "SELECT id, name FROM items ORDER BY name"
            ).fetchall()
            item_dicts = [dict(r) for r in items]
            assert len(item_dicts) >= 2, f"Expected ≥2 items, got {len(item_dicts)}"

            db.close()

    def test_hardcoded_seed_applied_when_no_files(self):
        """When no cache files exist, the 6 hardcoded champions are seeded."""
        from arena_buddy.db.seed import _seed_from_files, _seed_champions
        from arena_buddy.db.schema import create_all

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "nonexistent"

            db = sqlite3.connect(Path(tmp) / "test.db")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            create_all(db)

            with patch("arena_buddy.db.seed._CACHE_DIR", cache):
                # _seed_from_files should be a no-op when no files exist
                _seed_from_files(db)
                # Then _seed_champions adds the hardcoded 6
                _seed_champions(db)

            db.commit()
            champions = db.execute("SELECT COUNT(*) AS c FROM champions").fetchone()
            assert champions["c"] == 6, f"Expected 6 hardcoded champions, got {champions['c']}"

            db.close()

    def test_augments_import_when_file_present(self):
        """When augments.json exists alongside the other files, augments are imported."""
        from arena_buddy.db.seed import _seed_from_files, _CACHE_DIR
        from arena_buddy.db.schema import create_all

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)

            # Champions
            champ_data = {
                "data": {
                    "Lucian": {
                        "key": "236", "name": "Lucian",
                        "id": "Lucian", "image": {"full": "Lucian.png"}
                    },
                }
            }
            (cache / "champions.json").write_text(json.dumps(champ_data))

            # Items
            item_data = {
                "data": {
                    "1001": {
                        "name": "Boots", "image": {"full": "1001.png"},
                        "gold": {"total": 300}, "plaintext": "Basic boots"
                    },
                }
            }
            (cache / "items.json").write_text(json.dumps(item_data))

            # Augments
            augment_data = {
                "augments": [
                    {
                        "apiName": "TestAugment",
                        "name": "Test Augment",
                        "rarity": 2,
                        "desc": "A test augment",
                        "iconSmall": "/icons/TestAugment.png",
                    },
                ]
            }
            (cache / "augments.json").write_text(json.dumps(augment_data))

            db = sqlite3.connect(Path(tmp) / "test.db")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            create_all(db)

            with patch("arena_buddy.db.seed._CACHE_DIR", cache):
                _seed_from_files(db)

            db.commit()
            augments = db.execute("SELECT * FROM augments").fetchall()
            assert len(augments) == 1, f"Expected 1 augment, got {len(augments)}"
            assert augments[0]["api_name"] == "TestAugment"

            db.close()


# ---------------------------------------------------------------------------
# Test: seed_all integration — full pipeline
# ---------------------------------------------------------------------------

class TestSeedAllPipeline:
    """End-to-end seed_all tests with various file states."""

    def test_seed_all_with_full_cache(self):
        """seed_all imports full dataset when all files present."""
        from arena_buddy.db.seed import seed_all, _CACHE_DIR
        from arena_buddy.db.schema import create_all

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)

            # Champions (172-ish subset for test)
            champs = {}
            for name, key in [("Aatrox", "266"), ("Ahri", "103"), ("Akali", "84"),
                              ("Ashe", "22"), ("Lucian", "236"), ("Zed", "238"),
                              ("Yasuo", "157"), ("Sett", "875"), ("Kaisa", "145")]:
                champs[name] = {
                    "key": key, "name": name,
                    "id": name, "image": {"full": f"{name}.png"}
                }
            (cache / "champions.json").write_text(json.dumps({"data": champs}))

            # Items
            items = {}
            for id_, name in [("1001", "Boots"), ("3078", "Trinity Force")]:
                items[id_] = {
                    "name": name, "image": {"full": f"{id_}.png"},
                    "gold": {"total": 1000}, "plaintext": name
                }
            (cache / "items.json").write_text(json.dumps({"data": items}))

            # Augments
            (cache / "augments.json").write_text(json.dumps({"augments": []}))

            db = sqlite3.connect(Path(tmp) / "test.db")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            create_all(db)

            with patch("arena_buddy.db.seed._CACHE_DIR", cache):
                # Also patch _download_data_files to skip HTTP
                with patch("arena_buddy.db.seed._download_data_files"):
                    seed_all(db)

            db.commit()
            champ_count = db.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]
            assert champ_count == 9, f"Expected 9 champions, got {champ_count}"

            db.close()

    def test_seed_all_no_cache_uses_hardcoded(self):
        """seed_all should fall back to 6 hardcoded champs when no cache files exist."""
        from arena_buddy.db.seed import seed_all, _CACHE_DIR
        from arena_buddy.db.schema import create_all

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "nonexistent"

            db = sqlite3.connect(Path(tmp) / "test.db")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            create_all(db)

            with patch("arena_buddy.db.seed._CACHE_DIR", cache):
                with patch("arena_buddy.db.seed._download_data_files"):
                    seed_all(db)

            db.commit()
            champ_count = db.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]
            assert champ_count == 6, f"Expected 6 hardcoded champions, got {champ_count}"

            db.close()

    def test_seed_all_idempotent(self):
        """Running seed_all twice should not duplicate data."""
        from arena_buddy.db.seed import seed_all, _CACHE_DIR
        from arena_buddy.db.schema import create_all

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "nonexistent"

            db = sqlite3.connect(Path(tmp) / "test.db")
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            create_all(db)

            with patch("arena_buddy.db.seed._CACHE_DIR", cache):
                with patch("arena_buddy.db.seed._download_data_files"):
                    seed_all(db)
                    first_count = db.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]
                    seed_all(db)
                    second_count = db.execute("SELECT COUNT(*) AS c FROM champions").fetchone()["c"]

            assert first_count == 6
            assert second_count == 6, "seed_all should be idempotent"

            db.close()
