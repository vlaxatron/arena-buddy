"""Comprehensive tests for the LoLalytics Arena scraper module.

Covers:
- champion_name_to_url_key()
- parse_win_rate() / parse_pick_rate() / parse_games()
- ItemStat, AugmentStat, ScrapeResult dataclasses
- scrape_champion() with mock HTTP responses
- store_champion_stats() with upsert logic
- RateLimiter class
- scrape_all_champions() orchestration
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict

import pytest

from arena_buddy.db.schema import create_all


# ============================================================================
# Mock HTML samples for testing parsing
# ============================================================================

MOCK_ITEMS_HTML = """
<table class="item_stats_table">
  <thead>
    <tr><th>Item</th><th>Win Rate</th><th>Pick Rate</th><th>Games</th></tr>
  </thead>
  <tbody>
    <tr>
      <td class="name">Kraken Slayer</td>
      <td class="winrate">56.2%</td>
      <td class="pickrate">38.4%</td>
      <td class="games">12.4k</td>
    </tr>
    <tr>
      <td class="name">Navori Flickerblade</td>
      <td class="winrate">55.8%</td>
      <td class="pickrate">42.1%</td>
      <td class="games">13.6k</td>
    </tr>
    <tr>
      <td class="name">Infinity Edge</td>
      <td class="winrate">54.9%</td>
      <td class="pickrate">28.9%</td>
      <td class="games">9.3k</td>
    </tr>
    <tr>
      <td class="name">Berserker's Greaves</td>
      <td class="winrate">52.8%</td>
      <td class="pickrate">65.2%</td>
      <td class="games">21.0k</td>
    </tr>
  </tbody>
</table>
"""

MOCK_AUGMENTS_HTML = """
<div class="augment_section">
  <h3>Prismatic Augments</h3>
  <table class="augment_stats_table">
    <thead>
      <tr><th>Augment</th><th>Win Rate</th><th>Pick Rate</th><th>Games</th></tr>
    </thead>
    <tbody>
      <tr class="prismatic">
        <td class="name">Back To Basics</td>
        <td class="winrate">63.2%</td>
        <td class="pickrate">12.4%</td>
        <td class="games">4.2k</td>
      </tr>
      <tr class="prismatic">
        <td class="name">Blade Waltz</td>
        <td class="winrate">61.8%</td>
        <td class="pickrate">8.7%</td>
        <td class="games">3.1k</td>
      </tr>
    </tbody>
  </table>
  <h3>Gold Augments</h3>
  <table class="augment_stats_table">
    <tbody>
      <tr class="gold">
        <td class="name">ADAPt</td>
        <td class="winrate">58.4%</td>
        <td class="pickrate">18.2%</td>
        <td class="games">6.2k</td>
      </tr>
      <tr class="gold">
        <td class="name">Bread And Butter</td>
        <td class="winrate">56.3%</td>
        <td class="pickrate">22.8%</td>
        <td class="games">7.8k</td>
      </tr>
    </tbody>
  </table>
  <h3>Silver Augments</h3>
  <table class="augment_stats_table">
    <tbody>
      <tr class="silver">
        <td class="name">Stats!</td>
        <td class="winrate">53.2%</td>
        <td class="pickrate">28.4%</td>
        <td class="games">9.8k</td>
      </tr>
      <tr class="silver">
        <td class="name">Warmup Routine</td>
        <td class="winrate">52.1%</td>
        <td class="pickrate">19.2%</td>
        <td class="games">6.6k</td>
      </tr>
    </tbody>
  </table>
</div>
"""

FULL_MOCK_PAGE = f"""
<!DOCTYPE html>
<html>
<head><title>Lucian Arena Build - LoLalytics</title></head>
<body>
  <div id="content">
    <h1>Lucian Arena Build</h1>
    <h2>Best Items</h2>
    {MOCK_ITEMS_HTML}
    <h2>Best Augments</h2>
    {MOCK_AUGMENTS_HTML}
  </div>
</body>
</html>
"""

# Edge-case mock: empty tables, missing values
MOCK_EMPTY_PAGE = """
<!DOCTYPE html>
<html>
<body>
  <h1>Some Champion Arena Build</h1>
  <p>No data available for this patch.</p>
</body>
</html>
"""


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def scraper_db(temp_db_path):
    """Database with schema created, ready for scraper storage tests."""
    conn = sqlite3.connect(str(temp_db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    create_all(conn)

    # Insert a champion, items, augments, and patch for foreign keys
    conn.execute(
        "INSERT INTO champions (id, key, name) VALUES (236, 'Lucian', 'Lucian')"
    )
    conn.execute(
        "INSERT INTO patches (id, version, is_current) VALUES (1, '16.11', 1)"
    )
    conn.executemany(
        "INSERT INTO items (id, name) VALUES (?, ?)",
        [
            (6672, "Kraken Slayer"),
            (6675, "Navori Flickerblade"),
            (3031, "Infinity Edge"),
            (3006, "Berserker's Greaves"),
        ],
    )
    conn.executemany(
        "INSERT INTO augments (id, api_name, name, rarity) VALUES (?, ?, ?, ?)",
        [
            (101, "BackToBasics", "Back To Basics", 2),
            (102, "BladeWaltz", "Blade Waltz", 2),
            (201, "ADAPt", "ADAPt", 1),
            (301, "Stats", "Stats!", 0),
        ],
    )
    conn.commit()
    yield conn
    conn.close()


# ============================================================================
# Test champion_name_to_url_key
# ============================================================================

class TestChampionNameToUrlKey:
    """Verify champion name to URL-friendly key conversion."""

    def test_simple_name_lowercase(self):
        """Standard name is lowercased."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Lucian") == "lucian"
        assert champion_name_to_url_key("Ahri") == "ahri"
        assert champion_name_to_url_key("Zed") == "zed"

    def test_nunu_and_willump(self):
        """Nunu & Willump → nunu."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Nunu & Willump") == "nunu"

    def test_wukong_to_monkeyking(self):
        """Wukong → monkeyking."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Wukong") == "monkeyking"

    def test_kaisa_removes_apostrophe(self):
        """Kai'Sa → kaisa."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Kai'Sa") == "kaisa"

    def test_multiple_apostrophes(self):
        """Names with apostrophes have them removed and are lowercased."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Rek'Sai") == "reksai"
        assert champion_name_to_url_key("Cho'Gath") == "chogath"
        assert champion_name_to_url_key("Kha'Zix") == "khazix"
        assert champion_name_to_url_key("Vel'Koz") == "velkoz"
        assert champion_name_to_url_key("Bel'Veth") == "belveth"

    def test_multi_word_names(self):
        """Multi-word names have spaces removed."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Miss Fortune") == "missfortune"
        assert champion_name_to_url_key("Master Yi") == "masteryi"
        assert champion_name_to_url_key("Lee Sin") == "leesin"
        assert champion_name_to_url_key("Twisted Fate") == "twistedfate"
        assert champion_name_to_url_key("Jarvan IV") == "jarvaniv"

    def test_special_chars_removed(self):
        """Special characters (periods, dots) are removed."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("Dr. Mundo") == "drmundo"

    def test_all_special_cases_exist_in_map(self):
        """Every known special case has a mapping and doesn't crash."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key

        known_cases = {
            "Nunu & Willump": "nunu",
            "Wukong": "monkeyking",
            "Kai'Sa": "kaisa",
            "Rek'Sai": "reksai",
            "Cho'Gath": "chogath",
            "Kha'Zix": "khazix",
            "Vel'Koz": "velkoz",
            "Bel'Veth": "belveth",
            "Miss Fortune": "missfortune",
            "Master Yi": "masteryi",
            "Lee Sin": "leesin",
            "Twisted Fate": "twistedfate",
            "Jarvan IV": "jarvaniv",
            "Xin Zhao": "xinzhao",
            "Tahm Kench": "tahmkench",
            "Aurelion Sol": "aurelionsol",
            "Dr. Mundo": "drmundo",
        }
        for name, expected in known_cases.items():
            result = champion_name_to_url_key(name)
            assert result == expected, f"Expected {name!r} → {expected!r}, got {result!r}"

    def test_already_lowercase_without_special_chars(self):
        """Input that's already clean returns identical output."""
        from arena_buddy.scraper.lolalytics import champion_name_to_url_key
        assert champion_name_to_url_key("lucian") == "lucian"
        assert champion_name_to_url_key("ahri") == "ahri"


# ============================================================================
# Test parse_* functions
# ============================================================================

class TestParseWinRate:
    """Verify percentage string parsing."""

    def test_standard_percentage(self):
        from arena_buddy.scraper.lolalytics import parse_win_rate
        assert parse_win_rate("56.2%") == pytest.approx(0.562)
        assert parse_win_rate("55.8%") == pytest.approx(0.558)
        assert parse_win_rate("63.2%") == pytest.approx(0.632)

    def test_one_hundred_percent(self):
        from arena_buddy.scraper.lolalytics import parse_win_rate
        assert parse_win_rate("100%") == pytest.approx(1.0)
        assert parse_win_rate("100.0%") == pytest.approx(1.0)

    def test_zero_percent(self):
        from arena_buddy.scraper.lolalytics import parse_win_rate
        assert parse_win_rate("0%") == pytest.approx(0.0)
        assert parse_win_rate("0.0%") == pytest.approx(0.0)

    def test_no_percent_sign(self):
        from arena_buddy.scraper.lolalytics import parse_win_rate
        assert parse_win_rate("56.2") == pytest.approx(0.562)

    def test_whitespace_handling(self):
        from arena_buddy.scraper.lolalytics import parse_win_rate
        assert parse_win_rate("  56.2%  ") == pytest.approx(0.562)

    def test_none_or_empty(self):
        from arena_buddy.scraper.lolalytics import parse_win_rate
        assert parse_win_rate("") == 0.0
        assert parse_win_rate(None) == 0.0  # type: ignore[arg-type]


class TestParsePickRate:
    """Verify pick rate parsing (same pattern as win rate)."""

    def test_standard(self):
        from arena_buddy.scraper.lolalytics import parse_pick_rate
        assert parse_pick_rate("38.4%") == pytest.approx(0.384)

    def test_zero(self):
        from arena_buddy.scraper.lolalytics import parse_pick_rate
        assert parse_pick_rate("0%") == pytest.approx(0.0)

    def test_none(self):
        from arena_buddy.scraper.lolalytics import parse_pick_rate
        assert parse_pick_rate(None) == 0.0  # type: ignore[arg-type]


class TestParseGames:
    """Verify games-played string parsing (k-suffix handling)."""

    def test_k_suffix(self):
        from arena_buddy.scraper.lolalytics import parse_games
        assert parse_games("12.4k") == 12400
        assert parse_games("9.3k") == 9300
        assert parse_games("21.0k") == 21000
        assert parse_games("4.2k") == 4200

    def test_plain_integer(self):
        from arena_buddy.scraper.lolalytics import parse_games
        assert parse_games("850") == 850
        assert parse_games("12400") == 12400

    def test_k_suffix_case_insensitive(self):
        from arena_buddy.scraper.lolalytics import parse_games
        assert parse_games("12.4K") == 12400
        assert parse_games("9.3k") == 9300

    def test_whitespace(self):
        from arena_buddy.scraper.lolalytics import parse_games
        assert parse_games("  12.4k  ") == 12400

    def test_m_suffix(self):
        """Millions: 1.2m → 1,200,000."""
        from arena_buddy.scraper.lolalytics import parse_games
        assert parse_games("1.2M") == 1200000
        assert parse_games("2.5m") == 2500000

    def test_none_or_empty(self):
        from arena_buddy.scraper.lolalytics import parse_games
        assert parse_games("") == 0
        assert parse_games(None) == 0  # type: ignore[arg-type]


# ============================================================================
# Test dataclasses
# ============================================================================

class TestItemStat:
    """Verify ItemStat dataclass."""

    def test_creation(self):
        from arena_buddy.scraper.lolalytics import ItemStat
        item = ItemStat(
            id=6672,
            name="Kraken Slayer",
            win_rate=0.562,
            pick_rate=0.384,
            games_played=12400,
            rank=1,
        )
        assert item.id == 6672
        assert item.name == "Kraken Slayer"
        assert item.win_rate == pytest.approx(0.562)
        assert item.pick_rate == pytest.approx(0.384)
        assert item.games_played == 12400
        assert item.rank == 1

    def test_optional_id(self):
        """ItemStat id can be None when name matching is needed."""
        from arena_buddy.scraper.lolalytics import ItemStat
        item = ItemStat(
            id=None,
            name="Unknown Item",
            win_rate=0.5,
            pick_rate=0.1,
            games_played=100,
            rank=5,
        )
        assert item.id is None
        assert item.name == "Unknown Item"

    def test_to_dict(self):
        from arena_buddy.scraper.lolalytics import ItemStat
        item = ItemStat(
            id=6672, name="Kraken Slayer",
            win_rate=0.562, pick_rate=0.384,
            games_played=12400, rank=1,
        )
        d = asdict(item)
        assert d["id"] == 6672
        assert d["win_rate"] == pytest.approx(0.562)


class TestAugmentStat:
    """Verify AugmentStat dataclass."""

    def test_creation(self):
        from arena_buddy.scraper.lolalytics import AugmentStat
        aug = AugmentStat(
            id=101,
            name="Back To Basics",
            rarity=2,
            win_rate=0.632,
            pick_rate=0.124,
            games_played=4200,
            rank=1,
        )
        assert aug.id == 101
        assert aug.name == "Back To Basics"
        assert aug.rarity == 2
        assert aug.win_rate == pytest.approx(0.632)

    def test_rarity_strings(self):
        """AugmentStat accepts rarity as string from HTML parsing."""
        from arena_buddy.scraper.lolalytics import AugmentStat
        aug = AugmentStat(
            id=None,
            name="Stats!",
            rarity="silver",
            win_rate=0.532,
            pick_rate=0.284,
            games_played=9800,
            rank=1,
        )
        assert aug.rarity == "silver"

    def test_to_dict(self):
        from arena_buddy.scraper.lolalytics import AugmentStat
        aug = AugmentStat(
            id=101, name="Back To Basics", rarity=2,
            win_rate=0.632, pick_rate=0.124,
            games_played=4200, rank=1,
        )
        d = asdict(aug)
        assert d["name"] == "Back To Basics"
        assert d["rarity"] == 2


class TestScrapeResult:
    """Verify ScrapeResult dataclass."""

    def test_empty_result(self):
        from arena_buddy.scraper.lolalytics import ScrapeResult
        result = ScrapeResult(items=[], augments=[])
        assert result.items == []
        assert result.augments == []

    def test_populated_result(self):
        from arena_buddy.scraper.lolalytics import ScrapeResult, ItemStat, AugmentStat
        items = [ItemStat(id=6672, name="Kraken Slayer", win_rate=0.562, pick_rate=0.384, games_played=12400, rank=1)]
        augments = [AugmentStat(id=101, name="Back To Basics", rarity=2, win_rate=0.632, pick_rate=0.124, games_played=4200, rank=1)]
        result = ScrapeResult(items=items, augments=augments)
        assert len(result.items) == 1
        assert len(result.augments) == 1
        assert result.items[0].name == "Kraken Slayer"
        assert result.augments[0].name == "Back To Basics"


# ============================================================================
# Test scrape_champion with mock HTTP
# ============================================================================

class TestScrapeChampion:
    """Verify scrape_champion fetches and parses correctly."""

    def test_scrape_parses_items(self, monkeypatch):
        """scrape_champion parses item stats from mock HTML."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_champion

        class MockResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        def mock_get(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        with httpx.Client() as client:
            result = scrape_champion(client, "Lucian", "16.11")

        assert len(result.items) == 4
        assert result.items[0].name == "Kraken Slayer"
        assert result.items[0].win_rate == pytest.approx(0.562)
        assert result.items[0].pick_rate == pytest.approx(0.384)
        assert result.items[0].games_played == 12400
        assert result.items[0].rank == 1
        # Last item in table
        assert result.items[3].name == "Berserker's Greaves"
        assert result.items[3].rank == 4

    def test_scrape_parses_augments(self, monkeypatch):
        """scrape_champion parses augment stats from mock HTML, including rarity."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_champion

        class MockResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        def mock_get(*args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        with httpx.Client() as client:
            result = scrape_champion(client, "Lucian", "16.11")

        assert len(result.augments) == 6

        # Prismatic augments first
        prismatic = [a for a in result.augments if a.rarity == "prismatic"]
        assert len(prismatic) == 2
        assert prismatic[0].name == "Back To Basics"
        assert prismatic[0].win_rate == pytest.approx(0.632)

        # Gold augments
        gold = [a for a in result.augments if a.rarity == "gold"]
        assert len(gold) == 2

        # Silver augments
        silver = [a for a in result.augments if a.rarity == "silver"]
        assert len(silver) == 2

    def test_scrape_uses_correct_url(self, monkeypatch):
        """scrape_champion builds the correct LoLalytics URL."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_champion

        captured_urls = []

        class MockResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        def mock_get(self, url, **kwargs):
            captured_urls.append(url)
            return MockResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        with httpx.Client() as client:
            scrape_champion(client, "Lucian", "16.11")

        assert len(captured_urls) == 1
        assert "lolalytics.com" in captured_urls[0]
        assert "/lucian/" in captured_urls[0]
        assert "/arena/" in captured_urls[0]
        assert "16.11" in captured_urls[0]

    def test_scrape_with_special_champion_name(self, monkeypatch):
        """scrape_champion handles special champion names (Wukong → monkeyking)."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_champion

        captured_urls = []

        class MockResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        def mock_get(self, url, **kwargs):
            captured_urls.append(url)
            return MockResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        with httpx.Client() as client:
            scrape_champion(client, "Wukong", "16.11")

        assert "/monkeyking/" in captured_urls[0]

    def test_scrape_empty_page(self, monkeypatch):
        """scrape_champion returns empty result when page has no tables."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_champion

        class MockResponse:
            status_code = 200
            text = MOCK_EMPTY_PAGE
            def raise_for_status(self):
                pass

        monkeypatch.setattr(httpx.Client, "get", lambda self, url: MockResponse())

        with httpx.Client() as client:
            result = scrape_champion(client, "SomeChamp", "16.11")

        assert result.items == []
        assert result.augments == []

    def test_scrape_http_error_raises(self, monkeypatch):
        """scrape_champion raises on HTTP error status."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_champion

        class MockResponse:
            status_code = 404
            text = "Not Found"
            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "Not Found", request=object(), response=self  # type: ignore[arg-type]
                )

        monkeypatch.setattr(httpx.Client, "get", lambda self, url: MockResponse())

        with httpx.Client() as client:
            with pytest.raises(httpx.HTTPStatusError):
                scrape_champion(client, "Lucian", "16.11")


# ============================================================================
# Test store_champion_stats
# ============================================================================

class TestStoreChampionStats:
    """Verify store_champion_stats upserts into global stats tables."""

    def test_store_items(self, scraper_db):
        """store_champion_stats inserts item stats."""
        from arena_buddy.scraper.lolalytics import (
            store_champion_stats,
            ScrapeResult,
            ItemStat,
        )

        result = ScrapeResult(
            items=[
                ItemStat(id=6672, name="Kraken Slayer", win_rate=0.562, pick_rate=0.384, games_played=12400, rank=1),
                ItemStat(id=6675, name="Navori Flickerblade", win_rate=0.558, pick_rate=0.421, games_played=13600, rank=2),
            ],
            augments=[],
        )

        store_champion_stats(scraper_db, champion_id=236, patch_id=1, result=result)

        rows = scraper_db.execute(
            "SELECT item_id, win_rate, pick_rate, games_played, rank "
            "FROM global_item_stats WHERE champion_id = 236 AND patch_id = 1 "
            "ORDER BY rank"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["item_id"] == 6672
        assert rows[0]["win_rate"] == pytest.approx(0.562)
        assert rows[0]["rank"] == 1

    def test_store_augments(self, scraper_db):
        """store_champion_stats inserts augment stats."""
        from arena_buddy.scraper.lolalytics import (
            store_champion_stats,
            ScrapeResult,
            AugmentStat,
        )

        result = ScrapeResult(
            items=[],
            augments=[
                AugmentStat(id=101, name="Back To Basics", rarity=2, win_rate=0.632, pick_rate=0.124, games_played=4200, rank=1),
                AugmentStat(id=301, name="Stats!", rarity=0, win_rate=0.532, pick_rate=0.284, games_played=9800, rank=1),
            ],
        )

        store_champion_stats(scraper_db, champion_id=236, patch_id=1, result=result)

        rows = scraper_db.execute(
            "SELECT augment_id, rarity, win_rate, pick_rate, games_played, rank "
            "FROM global_augment_stats WHERE champion_id = 236 AND patch_id = 1 "
            "ORDER BY rarity DESC, rank"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["augment_id"] == 101
        assert rows[0]["rarity"] == 2
        assert rows[0]["win_rate"] == pytest.approx(0.632)

    def test_upsert_overwrites_existing(self, scraper_db):
        """store_champion_stats upserts: same keys get updated."""
        from arena_buddy.scraper.lolalytics import (
            store_champion_stats,
            ScrapeResult,
            ItemStat,
        )

        # First insert
        result1 = ScrapeResult(
            items=[ItemStat(id=6672, name="Kraken Slayer", win_rate=0.562, pick_rate=0.384, games_played=12400, rank=1)],
            augments=[],
        )
        store_champion_stats(scraper_db, 236, 1, result1)

        # Second insert with updated values
        result2 = ScrapeResult(
            items=[ItemStat(id=6672, name="Kraken Slayer", win_rate=0.570, pick_rate=0.400, games_played=13000, rank=2)],
            augments=[],
        )
        store_champion_stats(scraper_db, 236, 1, result2)

        # Should still be 1 row, but with updated values
        rows = scraper_db.execute(
            "SELECT win_rate, pick_rate, games_played, rank FROM global_item_stats "
            "WHERE champion_id = 236 AND patch_id = 1 AND item_id = 6672"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["win_rate"] == pytest.approx(0.570)
        assert rows[0]["rank"] == 2

    def test_store_skips_none_id(self, scraper_db):
        """Items/augments with id=None are skipped during storage."""
        from arena_buddy.scraper.lolalytics import (
            store_champion_stats,
            ScrapeResult,
            ItemStat,
            AugmentStat,
        )

        result = ScrapeResult(
            items=[
                ItemStat(id=None, name="Unknown", win_rate=0.5, pick_rate=0.1, games_played=100, rank=1),
                ItemStat(id=6672, name="Kraken Slayer", win_rate=0.562, pick_rate=0.384, games_played=12400, rank=1),
            ],
            augments=[
                AugmentStat(id=None, name="Unknown", rarity=2, win_rate=0.5, pick_rate=0.1, games_played=100, rank=1),
            ],
        )

        store_champion_stats(scraper_db, 236, 1, result)

        item_rows = scraper_db.execute(
            "SELECT COUNT(*) as cnt FROM global_item_stats WHERE champion_id = 236"
        ).fetchone()
        assert item_rows["cnt"] == 1  # Only the known item

        aug_rows = scraper_db.execute(
            "SELECT COUNT(*) as cnt FROM global_augment_stats WHERE champion_id = 236"
        ).fetchone()
        assert aug_rows["cnt"] == 0  # None-id augment skipped


# ============================================================================
# Test RateLimiter
# ============================================================================

class TestRateLimiter:
    """Verify RateLimiter enforces minimum delay between requests."""

    def test_first_call_no_delay(self):
        """First call to RateLimiter should have no delay."""
        from arena_buddy.scraper.lolalytics import RateLimiter
        rl = RateLimiter(min_interval=1.0)
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.5  # Should be near-instant

    def test_subsequent_call_waits(self):
        """Second call within min_interval should wait."""
        from arena_buddy.scraper.lolalytics import RateLimiter
        rl = RateLimiter(min_interval=0.1)
        rl.wait()
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        # With 0.1s interval, it should wait ~0.1s
        # Allow some tolerance for scheduling jitter
        assert 0.05 <= elapsed <= 0.3

    def test_call_after_interval_no_wait(self):
        """Call after the interval has passed should have no delay."""
        from arena_buddy.scraper.lolalytics import RateLimiter
        rl = RateLimiter(min_interval=0.05)
        rl.wait()
        time.sleep(0.1)  # Wait longer than the interval
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_different_rates(self):
        """RateLimiter works with different min intervals."""
        from arena_buddy.scraper.lolalytics import RateLimiter
        rl = RateLimiter(min_interval=0.5)
        rl.wait()
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.4  # Should have waited ~0.5s


# ============================================================================
# Test scrape_all_champions orchestration
# ============================================================================

class TestScrapeAllChampions:
    """Verify scrape_all_champions orchestrates a full scrape."""

    def test_scrapes_multiple_champions(self, monkeypatch, scraper_db):
        """scrape_all_champions scrapes each champion and stores results."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_all_champions

        call_count = 0

        class MockResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        def mock_get(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return MockResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        champions = [
            {"id": 236, "key": "Lucian", "name": "Lucian"},
            {"id": 1, "key": "Ahri", "name": "Ahri"},
        ]

        scrape_all_champions(scraper_db, champions, "16.11")

        assert call_count == 2

    def test_respects_rate_limit(self, monkeypatch, scraper_db):
        """scrape_all_champions enforces rate limiting between champions."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_all_champions

        call_times = []

        class MockResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        def mock_get(self, url, **kwargs):
            call_times.append(time.monotonic())
            return MockResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        champions = [
            {"id": 236, "key": "Lucian", "name": "Lucian"},
            {"id": 1, "key": "Ahri", "name": "Ahri"},
            {"id": 2, "key": "Zed", "name": "Zed"},
        ]

        scrape_all_champions(scraper_db, champions, "16.11", rate_limit=0.1)

        # Check that there were delays between calls
        assert len(call_times) == 3
        for i in range(1, len(call_times)):
            gap = call_times[i] - call_times[i - 1]
            assert gap >= 0.08  # Allow small tolerance

    def test_handles_scrape_error_and_continues(self, monkeypatch, scraper_db):
        """scrape_all_champions continues scraping when one champion fails."""
        import httpx
        from arena_buddy.scraper.lolalytics import scrape_all_champions

        call_attempts = []

        class SuccessResponse:
            status_code = 200
            text = FULL_MOCK_PAGE
            def raise_for_status(self):
                pass

        class ErrorResponse:
            status_code = 503
            text = "Service Unavailable"
            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "Service Unavailable", request=object(), response=self  # type: ignore[arg-type]
                )

        def mock_get(self, url, **kwargs):
            call_attempts.append(url)
            if "ahri" in url:
                return ErrorResponse()
            return SuccessResponse()

        monkeypatch.setattr(httpx.Client, "get", mock_get)

        champions = [
            {"id": 236, "key": "Lucian", "name": "Lucian"},
            {"id": 1, "key": "Ahri", "name": "Ahri"},  # Will fail
            {"id": 2, "key": "Zed", "name": "Zed"},
        ]

        # Should not raise — errors are caught and logged
        scrape_all_champions(scraper_db, champions, "16.11", rate_limit=0.0)

        # All 3 champions were attempted
        assert len(call_attempts) == 3
