"""LoLalytics Arena scraper — fetches and parses champion item/augment stats.

Usage::

    import httpx
    from arena_buddy.scraper.lolalytics import scrape_champion, store_champion_stats

    with httpx.Client() as client:
        result = scrape_champion(client, "Lucian", "16.11")
    store_champion_stats(conn, champion_id=236, patch_id=1, result=result)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ============================================================================
# URL & champion name helpers
# ============================================================================

# Known special URL key mappings (Data Dragon key → LoLalytics URL slug).
# Falls back to: lowercase, strip apostrophes & dots, remove spaces.
_CHAMPION_URL_MAP: dict[str, str] = {
    "Nunu & Willump": "nunu",
    "Wukong": "monkeyking",
}

# Pattern for cleaning champion names into URL keys
_RE_APOSTROPHE = re.compile(r"['']")
_RE_DOT = re.compile(r"\.+")
_RE_SPACE = re.compile(r"\s+")


def champion_name_to_url_key(name: str) -> str:
    """Convert a Data Dragon champion key into a LoLalytics URL slug.

    Examples::

        >>> champion_name_to_url_key("Lucian")
        'lucian'
        >>> champion_name_to_url_key("Nunu & Willump")
        'nunu'
        >>> champion_name_to_url_key("Kai'Sa")
        'kaisa'
        >>> champion_name_to_url_key("Wukong")
        'monkeyking'
    """
    # Check known special cases first
    if name in _CHAMPION_URL_MAP:
        return _CHAMPION_URL_MAP[name]

    # Generic transformation
    key = name.lower()
    key = _RE_APOSTROPHE.sub("", key)       # Kai'Sa → kaisa
    key = _RE_DOT.sub("", key)              # Dr. Mundo → drmundo
    key = _RE_SPACE.sub("", key)            # Miss Fortune → missfortune
    return key


def _build_arena_url(champion_key: str, patch: str) -> str:
    """Build the LoLalytics arena build URL for a champion."""
    slug = champion_name_to_url_key(champion_key)
    return f"https://lolalytics.com/lol/{slug}/arena/build/?patch={patch}"


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class ItemStat:
    """A single item stat row scraped from LoLalytics."""

    id: int | None
    name: str
    win_rate: float
    pick_rate: float
    games_played: int
    rank: int


@dataclass
class AugmentStat:
    """A single augment stat row scraped from LoLalytics."""

    id: int | None
    name: str
    rarity: int | str  # 0=silver, 1=gold, 2=prismatic, or raw string from HTML
    win_rate: float
    pick_rate: float
    games_played: int
    rank: int


@dataclass
class ScrapeResult:
    """Result of scraping a single champion's arena page."""

    items: list[ItemStat] = field(default_factory=list)
    augments: list[AugmentStat] = field(default_factory=list)


# ============================================================================
# Parsing helpers
# ============================================================================

def parse_win_rate(text: str | None) -> float:
    """Parse a win-rate percentage string into a float (0.0–1.0).

    >>> parse_win_rate("56.2%")
    0.562
    >>> parse_win_rate("")
    0.0
    """
    if not text:
        return 0.0
    cleaned = text.strip().replace("%", "")
    try:
        value = float(cleaned)
        return value / 100.0
    except (ValueError, TypeError):
        return 0.0


def parse_pick_rate(text: str | None) -> float:
    """Parse a pick-rate percentage string into a float (0.0–1.0).

    Same logic as :func:`parse_win_rate`.
    """
    return parse_win_rate(text)  # Same logic: percentage → 0.0-1.0


def parse_games(text: str | None) -> int:
    """Parse a games-played string into an integer, handling k/m suffixes.

    >>> parse_games("12.4k")
    12400
    >>> parse_games("850")
    850
    >>> parse_games("1.2M")
    1200000
    """
    if not text:
        return 0
    cleaned = text.strip().lower()
    multiplier = 1
    if cleaned.endswith("m"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("k"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except (ValueError, TypeError):
        return 0


# ============================================================================
# HTML parsing
# ============================================================================

def _parse_items_table(soup: BeautifulSoup) -> list[ItemStat]:
    """Extract item stats from parsed HTML.

    Looks for ``<table class="item_stats_table">`` rows with
    ``.name``, ``.winrate``, ``.pickrate``, ``.games`` cells.
    """
    table = soup.find("table", class_="item_stats_table")
    if not table:
        logger.debug("No item_stats_table found in HTML")
        return []

    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")

    items: list[ItemStat] = []
    for idx, row in enumerate(rows, start=1):
        name_el = row.find("td", class_="name")
        wr_el = row.find("td", class_="winrate")
        pr_el = row.find("td", class_="pickrate")
        games_el = row.find("td", class_="games")

        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        win_rate = parse_win_rate(wr_el.get_text(strip=True) if wr_el else "")
        pick_rate = parse_pick_rate(pr_el.get_text(strip=True) if pr_el else "")
        games_played = parse_games(games_el.get_text(strip=True) if games_el else "")

        items.append(ItemStat(
            id=None,
            name=name,
            win_rate=win_rate,
            pick_rate=pick_rate,
            games_played=games_played,
            rank=idx,
        ))
    return items


_RARITY_MAP = {
    "prismatic": "prismatic",
    "gold": "gold",
    "silver": "silver",
}


def _parse_augments_section(soup: BeautifulSoup) -> list[AugmentStat]:
    """Extract augment stats from parsed HTML.

    Looks for ``<table class="augment_stats_table">`` rows and
    infers rarity from the row's CSS class.
    """
    tables = soup.find_all("table", class_="augment_stats_table")
    if not tables:
        logger.debug("No augment_stats_table found in HTML")
        return []

    augments: list[AugmentStat] = []
    rank_counter: dict[str, int] = {}  # rarity → current rank

    for table in tables:
        # Determine rarity from preceding h3 or from row class
        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")

        for row in rows:
            name_el = row.find("td", class_="name")
            wr_el = row.find("td", class_="winrate")
            pr_el = row.find("td", class_="pickrate")
            games_el = row.find("td", class_="games")

            if not name_el:
                continue

            # Infer rarity from row's class attribute
            row_classes = row.get("class", [])
            rarity_str = "unknown"
            for cls in row_classes:
                if cls in _RARITY_MAP:
                    rarity_str = _RARITY_MAP[cls]
                    break

            # Default rarity if not found on row: check table parent
            if rarity_str == "unknown":
                rarity_str = _infer_rarity_from_context(table)

            # Calculate per-rarity rank
            if rarity_str not in rank_counter:
                rank_counter[rarity_str] = 0
            rank_counter[rarity_str] += 1
            rank = rank_counter[rarity_str]

            name = name_el.get_text(strip=True)
            win_rate = parse_win_rate(wr_el.get_text(strip=True) if wr_el else "")
            pick_rate = parse_pick_rate(pr_el.get_text(strip=True) if pr_el else "")
            games_played = parse_games(games_el.get_text(strip=True) if games_el else "")

            augments.append(AugmentStat(
                id=None,
                name=name,
                rarity=rarity_str,
                win_rate=win_rate,
                pick_rate=pick_rate,
                games_played=games_played,
                rank=rank,
            ))
    return augments


def _infer_rarity_from_context(table: Tag) -> str:
    """Try to determine augment rarity from surrounding HTML.

    Checks the preceding ``<h3>`` element for keywords.
    """
    prev = table.find_previous("h3")
    if prev:
        text = prev.get_text(strip=True).lower()
        if "prismatic" in text:
            return "prismatic"
        if "gold" in text:
            return "gold"
        if "silver" in text:
            return "silver"
    return "unknown"


# ============================================================================
# Main scraper functions
# ============================================================================

def scrape_champion(
    client: httpx.Client,
    champion_key: str,
    patch: str,
) -> ScrapeResult:
    """Fetch and parse the LoLalytics arena build page for a champion.

    Args:
        client: An ``httpx.Client`` instance (allows connection reuse).
        champion_key: Data Dragon champion key (e.g. ``"Lucian"``).
        patch: Patch version string (e.g. ``"16.11"``).

    Returns:
        A :class:`ScrapeResult` with extracted items and augments.

    Raises:
        httpx.HTTPStatusError: If the HTTP request fails.
    """
    url = _build_arena_url(champion_key, patch)
    logger.info("Scraping %s for patch %s → %s", champion_key, patch, url)

    response = client.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    items = _parse_items_table(soup)
    augments = _parse_augments_section(soup)

    logger.info(
        "Parsed %d items and %d augments for %s",
        len(items), len(augments), champion_key,
    )
    return ScrapeResult(items=items, augments=augments)


def store_champion_stats(
    conn: Any,
    champion_id: int,
    patch_id: int,
    result: ScrapeResult,
) -> None:
    """Upsert scraped champion stats into the database.

    Items/augments with ``id is None`` are silently skipped (they
    couldn't be matched to the items/augments reference tables).

    Args:
        conn: An open ``sqlite3.Connection``.
        champion_id: Database ID of the champion.
        patch_id: Database ID of the patch.
        result: The scraped :class:`ScrapeResult`.
    """
    for item in result.items:
        if item.id is None:
            continue
        conn.execute(
            """
            INSERT INTO global_item_stats
                (champion_id, item_id, patch_id, win_rate, pick_rate, games_played, rank)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(champion_id, item_id, patch_id) DO UPDATE SET
                win_rate = excluded.win_rate,
                pick_rate = excluded.pick_rate,
                games_played = excluded.games_played,
                rank = excluded.rank
            """,
            (champion_id, item.id, patch_id, item.win_rate, item.pick_rate,
             item.games_played, item.rank),
        )

    for aug in result.augments:
        if aug.id is None:
            continue
        # Convert rarity string to int for DB storage if needed
        rarity_int = _rarity_to_int(aug.rarity)
        conn.execute(
            """
            INSERT INTO global_augment_stats
                (champion_id, augment_id, patch_id, rarity, win_rate, pick_rate, games_played, rank)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(champion_id, augment_id, patch_id) DO UPDATE SET
                rarity = excluded.rarity,
                win_rate = excluded.win_rate,
                pick_rate = excluded.pick_rate,
                games_played = excluded.games_played,
                rank = excluded.rank
            """,
            (champion_id, aug.id, patch_id, rarity_int,
             aug.win_rate, aug.pick_rate, aug.games_played, aug.rank),
        )

    conn.commit()


def _rarity_to_int(rarity: int | str) -> int:
    """Convert a rarity string or int to the DB integer representation.

    - ``"prismatic"`` / ``2`` → 2
    - ``"gold"`` / ``1`` → 1
    - ``"silver"`` / ``0`` → 0
    - anything else → 0
    """
    if isinstance(rarity, int):
        return rarity
    mapping = {"prismatic": 2, "gold": 1, "silver": 0}
    return mapping.get(str(rarity).lower(), 0)


# ============================================================================
# Rate limiter
# ============================================================================

class RateLimiter:
    """Enforce a minimum interval between successive requests.

    Usage::

        rl = RateLimiter(min_interval=2.0)
        for champion in champions:
            rl.wait()
            scrape_champion(client, champion, patch)
    """

    def __init__(self, min_interval: float = 2.0) -> None:
        """Initialise the rate limiter.

        Args:
            min_interval: Minimum seconds between ``wait()`` calls.
        """
        self.min_interval = min_interval
        self._last_call: float = 0.0

    def wait(self) -> None:
        """Block until at least ``min_interval`` has elapsed since the last call."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if self._last_call > 0 and elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()


# ============================================================================
# Batch scraping
# ============================================================================

def scrape_all_champions(
    conn: Any,
    champions: list[dict[str, Any]],
    patch: str,
    *,
    rate_limit: float = 2.0,
) -> None:
    """Scrape arena stats for all champions and store them.

    Args:
        conn: An open ``sqlite3.Connection``.
        champions: List of champion dicts with ``id`` and ``key``.
        patch: Patch version string (e.g. ``"16.11"``).
        rate_limit: Minimum seconds between requests (default: 2.0).
    """
    rl = RateLimiter(min_interval=rate_limit)

    # Ensure patch record exists
    patch_id = _ensure_patch(conn, patch)

    with httpx.Client(timeout=30.0) as client:
        for champ in champions:
            rl.wait()
            try:
                result = scrape_champion(client, champ["key"], patch)
                store_champion_stats(conn, champ["id"], patch_id, result)
                logger.info(
                    "Stored %d items and %d augments for %s",
                    len(result.items), len(result.augments), champ["key"],
                )
            except Exception:
                logger.exception(
                    "Failed to scrape champion %s (patch %s)",
                    champ["key"], patch,
                )


def _ensure_patch(conn: Any, version: str) -> int:
    """Ensure a patch record exists in the database and return its ID.

    Creates the row if it doesn't exist (UPSERT).
    """
    conn.execute(
        """
        INSERT INTO patches (version, is_current)
        VALUES (?, 0)
        ON CONFLICT(version) DO NOTHING
        """,
        (version,),
    )
    row = conn.execute(
        "SELECT id FROM patches WHERE version = ?", (version,)
    ).fetchone()
    conn.commit()
    return row["id"] if row else 1
