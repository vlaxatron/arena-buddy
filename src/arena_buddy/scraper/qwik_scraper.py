"""Production LoLalytics scraper via Qwik JSON state decoding.

LoLalytics embeds ALL champion data in a ``<script type="qwik/json">`` tag.
The Qwik serialization uses base36-encoded indices into an object array.
By decoding these references we extract real augment win rates (hidden as
``xx.xx`` in the HTML) plus item stats.

CommunityDragon's ``arena/en_us.json`` uses the **same augment IDs** as
LoLalytics, providing the bridge to our database via ``apiName`` → ``api_name``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

from arena_buddy.scraper.lolalytics import (
    ItemStat, AugmentStat, ScrapeResult,
    champion_name_to_url_key, RateLimiter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CDragon JSON URL for augment ID → name mapping
_CDRAGON_URL = (
    "https://raw.communitydragon.org/latest/cdragon/arena/en_us.json"
)

# Cache the CDragon data for the lifetime of the process
_cdragon_cache: dict[int, tuple[str, str, int]] | None = None
_cdragon_api_index: dict[str, tuple[str, str, int]] | None = None


# ---------------------------------------------------------------------------
# CDragon augment mapping
# ---------------------------------------------------------------------------

def _load_cdragon() -> dict[int, tuple[str, str, int]]:
    """Load CommunityDragon augment ID → (name, apiName, rarity) mapping.

    Cached in memory; fetches from CDragon URL on first call.
    """
    global _cdragon_cache
    if _cdragon_cache is not None:
        return _cdragon_cache

    # Try local cache file first
    cache_path = Path.home() / ".cache" / "arena-buddy" / "data" / "cdragon_augments.json"
    data = None

    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            logger.debug("Loaded CDragon from cache: %s", cache_path)
        except Exception:
            logger.warning("Corrupt CDragon cache, re-fetching")

    if data is None:
        logger.info("Fetching CDragon augment data from %s", _CDRAGON_URL)
        req = urllib.request.Request(
            _CDRAGON_URL,
            headers={"User-Agent": "ArenaBuddy/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        # Cache locally
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data))
        logger.debug("Cached CDragon data to %s", cache_path)

    augs = data.get("augments", data) if isinstance(data, dict) else data
    _cdragon_cache = {}
    for a in augs:
        _cdragon_cache[a["id"]] = (
            a.get("name", ""),
            a.get("apiName", ""),
            a.get("rarity", 0),
        )
    logger.info("Loaded %d CDragon augment mappings", len(_cdragon_cache))
    return _cdragon_cache


def _build_api_index(
    conn: Any,
) -> dict[str, tuple[int, str, int]]:
    """Build ``api_name → (db_id, name, rarity)`` index from our DB.

    Only includes non-Special augments (rarity 0/1/2).
    Handles both ``sqlite3.Row`` and plain tuple results.
    """
    rows = conn.execute(
        "SELECT id, name, api_name, rarity FROM augments WHERE rarity IN (0,1,2)"
    ).fetchall()
    index: dict[str, tuple[int, str, int]] = {}
    for row in rows:
        if hasattr(row, "keys"):
            # sqlite3.Row
            api_name = row["api_name"] or ""
            db_id = row["id"]
            db_name = row["name"]
            db_rarity = row["rarity"]
        else:
            # Plain tuple
            db_id, db_name, api_name, db_rarity = row
            api_name = api_name or ""
        api_lower = api_name.lower()
        if api_lower:
            index[api_lower] = (db_id, db_name, db_rarity)
    return index


# ---------------------------------------------------------------------------
# Qwik state decoder
# ---------------------------------------------------------------------------

def _b36(s: str) -> int:
    """Convert base36 string to integer."""
    return int(s, 36)


def _resolve(objs: list[Any], ref: Any) -> Any:
    """Resolve a Qwik reference, following one level of indirection."""
    if not isinstance(ref, str):
        return ref
    try:
        idx = _b36(ref)
        if 0 <= idx < len(objs):
            return objs[idx]
    except (ValueError, TypeError):
        pass
    return ref


def _deep_resolve(objs: list[Any], val: Any, max_depth: int = 5) -> Any:
    """Keep resolving Qwik references until we hit a non-reference value."""
    for _ in range(max_depth):
        if isinstance(val, str) and len(val) <= 4:
            try:
                idx = _b36(val)
                if 0 <= idx < len(objs):
                    val = objs[idx]
                    continue
            except (ValueError, TypeError):
                pass
        break
    return val


def _extract_cards(
    objs: list[Any],
    card_list_ref: str,
) -> list[tuple[int, float, float, int]]:
    """Extract [id, win_rate, pick_rate, games] tuples from a card list.

    Each card in the Qwik state is a list of 4 references:
    ``[id_ref, wr_ref, pr_ref, games_ref]``.
    """
    card_list = _resolve(objs, card_list_ref)
    if not isinstance(card_list, list):
        return []

    result: list[tuple[int, float, float, int]] = []
    for card_ref in card_list:
        card = _resolve(objs, card_ref)
        if not isinstance(card, list) or len(card) < 4:
            continue
        try:
            item_id = int(_deep_resolve(objs, card[0]))
            wr = float(_deep_resolve(objs, card[1]))
            pr = float(_deep_resolve(objs, card[2]))
            games = int(_deep_resolve(objs, card[3]))
            result.append((item_id, wr, pr, games))
        except (ValueError, TypeError, IndexError):
            continue

    return result


# ---------------------------------------------------------------------------
# Champion scraper
# ---------------------------------------------------------------------------

def _find_champ_state(objs: list[Any]) -> dict[str, Any] | None:
    """Find the champion state object in the Qwik objs array.

    The champ state is a large dict with keys like ``augment``, ``items``,
    ``prismatic``, ``header``, etc.
    """
    for obj in objs:
        if isinstance(obj, dict) and "augment" in obj and "items" in obj:
            if "prismatic" in obj and "header" in obj:
                return obj
    return None


def _find_browser() -> str | None:
    """Find the Playwright Chromium headless shell binary."""
    import glob
    candidates = [
        "/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell",
    ]
    candidates += glob.glob(
        os.path.expanduser(
            "~/.playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        )
    )
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def scrape_champion_qwik(
    champion_key: str,
    patch: str,
    *,
    headless: bool = True,
    timeout: int = 30,
) -> ScrapeResult:
    """Scrape a champion from LoLalytics using Qwik JSON state decoding.

    Extracts items, prismatic items, starter items, and augments with
    **real win rates** (not ``xx.xx``).

    Args:
        champion_key: Data Dragon champion key (e.g. ``"Lucian"``).
        patch: Patch version string (e.g. ``"16.11"``).
        headless: Run browser in headless mode.
        timeout: Page load timeout in seconds.

    Returns:
        A :class:`ScrapeResult` with extracted items and augments.
    """
    from playwright.sync_api import sync_playwright

    url = f"https://lolalytics.com/lol/{champion_name_to_url_key(champion_key)}/arena/build/?patch={patch}"
    logger.info("Qwik-scraping %s", url)

    bexe = _find_browser()
    if not bexe:
        raise RuntimeError("Playwright Chromium headless shell not found")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=bexe,
            headless=headless,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1920, "height": 4000})
        try:
            page.goto(url, wait_until="load", timeout=timeout * 1000)
            time.sleep(4)

            # Accept consent banner
            try:
                page.click('button:has-text("Accept")', timeout=3000)
                time.sleep(2)
            except Exception:
                pass

            time.sleep(2)

            # Extract Qwik JSON state
            qwik_json = page.evaluate(
                """() => {
                    const s = document.querySelector('script[type="qwik/json"]');
                    return s ? s.textContent : null;
                }"""
            )

            if not qwik_json:
                raise ValueError("No Qwik JSON state found on page")

            data = json.loads(qwik_json)
            objs: list[Any] = data.get("objs", [])

            # Find champion state
            champ_state = _find_champ_state(objs)
            if champ_state is None:
                raise ValueError("Could not find champion state in Qwik data")

            # Extract items
            items: list[ItemStat] = []
            item_lists = {
                "items": champ_state.get("items"),
                "prismatic": champ_state.get("prismatic"),
                "startItem": champ_state.get("startItem"),
            }

            item_rank = 0
            for list_name, ref_id in item_lists.items():
                if ref_id is None:
                    continue
                cards = _extract_cards(objs, ref_id)
                for item_id, wr, pr, games in cards:
                    if item_id == 0:  # Skip placeholder/empty
                        continue
                    item_rank += 1
                    items.append(ItemStat(
                        id=item_id,
                        name="",  # Will be resolved by store function
                        win_rate=wr / 100.0,
                        pick_rate=pr / 100.0,
                        games_played=games,
                        rank=item_rank,
                    ))

            # Extract augments from "All Augments" (augment0)
            aug_obj = _resolve(objs, champ_state.get("augment"))
            augments: list[AugmentStat] = []

            if isinstance(aug_obj, dict):
                # Use augment0 (All Augments) — has the most cards
                aug_list_ref = aug_obj.get("augment0")
                if aug_list_ref:
                    cards = _extract_cards(objs, aug_list_ref)
                    aug_rank = 0
                    for item_id, wr, pr, games in cards:
                        aug_rank += 1
                        augments.append(AugmentStat(
                            id=item_id,
                            name="",  # Will be resolved by store function
                            rarity=0,  # Will be resolved from CDragon
                            win_rate=wr / 100.0,
                            pick_rate=pr / 100.0,
                            games_played=games,
                            rank=aug_rank,
                        ))

            logger.info(
                "%s: %d items, %d augments",
                champion_key, len(items), len(augments),
            )
            return ScrapeResult(items=items, augments=augments)

        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Store with CDragon mapping
# ---------------------------------------------------------------------------

def store_champion_stats_qwik(
    conn: Any,
    champion_id: int,
    patch_id: int,
    result: ScrapeResult,
) -> tuple[int, int]:
    """Store scraped stats using CDragon ID → DB ID mapping for augments.

    Unlike the old store function which expects IDs to already be DB IDs,
    this function maps LoLalytics/CDragon augment IDs to our database IDs
    via the ``api_name`` bridge.

    Args:
        conn: An open ``sqlite3.Connection``.
        champion_id: Database ID of the champion.
        patch_id: Database ID of the patch.
        result: The scraped :class:`ScrapeResult`.

    Returns:
        Tuple of ``(items_stored, augments_stored)`` counts.
    """
    cdragon = _load_cdragon()
    api_index = _build_api_index(conn)

    items_stored = 0
    for item in result.items:
        if item.id is None or item.id == 0:
            continue
        # Items use Data Dragon IDs directly — no mapping needed
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
            (champion_id, item.id, patch_id,
             item.win_rate, item.pick_rate, item.games_played, item.rank),
        )
        items_stored += 1

    augments_stored = 0
    for aug in result.augments:
        if aug.id is None:
            continue

        # Map LoLalytics/CDragon ID → our DB ID via apiName
        cd_entry = cdragon.get(aug.id)
        if cd_entry is None:
            continue

        cd_name, api_name, cd_rarity = cd_entry
        db_entry = api_index.get(api_name.lower())
        if db_entry is None:
            # Skip crafting/special augments not in our non-special DB
            continue

        db_id, db_name, db_rarity = db_entry

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
            (champion_id, db_id, patch_id, db_rarity,
             aug.win_rate, aug.pick_rate, aug.games_played, aug.rank),
        )
        augments_stored += 1

    conn.commit()
    logger.info(
        "Stored %d items, %d augments for champion %d",
        items_stored, augments_stored, champion_id,
    )
    return items_stored, augments_stored


# ---------------------------------------------------------------------------
# Full pipeline (scrape + store)
# ---------------------------------------------------------------------------

def scrape_and_store_qwik(
    conn: Any,
    champion_id: int,
    champion_key: str,
    patch: str,
    *,
    headless: bool = True,
) -> ScrapeResult:
    """Scrape a champion and store results using Qwik state decoding.

    Full pipeline: browser → Qwik JSON → decode → CDragon mapping → DB upsert.

    Args:
        conn: An open ``sqlite3.Connection``.
        champion_id: Database ID of the champion.
        champion_key: Data Dragon champion key (e.g. ``"Lucian"``).
        patch: Patch version string (e.g. ``"16.11"``).
        headless: Run browser in headless mode.

    Returns:
        The :class:`ScrapeResult` with items and augments.
    """
    # Ensure patch record exists
    prow = conn.execute(
        "SELECT id FROM patches WHERE version = ?", (patch,)
    ).fetchone()
    if not prow:
        conn.execute(
            "INSERT INTO patches (version, is_current) VALUES (?, 0)", (patch,)
        )
        conn.commit()
        prow = conn.execute(
            "SELECT id FROM patches WHERE version = ?", (patch,)
        ).fetchone()
    patch_id = prow[0]

    # Scrape
    result = scrape_champion_qwik(champion_key, patch, headless=headless)

    # Store
    store_champion_stats_qwik(conn, champion_id, patch_id, result)

    return result


# ---------------------------------------------------------------------------
# Batch scraping
# ---------------------------------------------------------------------------

def scrape_all_champions_qwik(
    conn: Any,
    champions: list[dict[str, Any]],
    patch: str,
    *,
    rate_limit: float = 3.0,
    headless: bool = True,
) -> dict[str, Any]:
    """Scrape arena stats for all champions using Qwik decoder.

    Args:
        conn: An open ``sqlite3.Connection``.
        champions: List of champion dicts with ``id`` and ``key``.
        patch: Patch version string (e.g. ``"16.11"``).
        rate_limit: Minimum seconds between requests (default: 3.0).
        headless: Run browser in headless mode.

    Returns:
        Dict with ``total``, ``success``, ``failed``, ``errors`` keys.
    """
    rl = RateLimiter(min_interval=rate_limit)

    # Ensure patch record exists
    prow = conn.execute(
        "SELECT id FROM patches WHERE version = ?", (patch,)
    ).fetchone()
    if not prow:
        conn.execute(
            "INSERT INTO patches (version, is_current) VALUES (?, 0)", (patch,)
        )
        conn.commit()
        prow = conn.execute(
            "SELECT id FROM patches WHERE version = ?", (patch,)
        ).fetchone()
    patch_id = prow[0]

    success = 0
    failed = 0
    errors: list[str] = []

    for i, champ in enumerate(champions):
        rl.wait()
        try:
            logger.info(
                "[%d/%d] Scraping %s...",
                i + 1, len(champions), champ["key"],
            )
            result = scrape_champion_qwik(
                champ["key"], patch, headless=headless,
            )
            items_n, augs_n = store_champion_stats_qwik(
                conn, champ["id"], patch_id, result,
            )
            logger.info(
                "[%d/%d] %s: %d items, %d augments stored",
                i + 1, len(champions), champ["key"], items_n, augs_n,
            )
            success += 1
        except Exception as exc:
            logger.exception("Failed to scrape %s", champ["key"])
            failed += 1
            errors.append(f"{champ['key']}: {exc}")

    return {
        "total": len(champions),
        "success": success,
        "failed": failed,
        "errors": errors,
    }
