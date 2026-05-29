"""Production LoLalytics browser scraper — precise DOM extraction.

Card structure (per item/augment):
  Item:  <img alt="NAME"> <div class="my-1">WR</div> <div class="my-1 text-[#939bf6]">PR</div> <div class="my-1 text-[9px] text-[#bbbbbb]">Games</div>
  Aug:   <img alt="NAME"> <div class="h-[16px] ...">Name</div> <div class="my-1 text-green-500">xx.xx</div> <div class="my-1 text-[#939bf6]">PR</div> <div class="my-1 text-[9px] text-[#bbbbbb]">Games</div>

Item WR is real (e.g. 53.85). Augment WR is hidden (xx.xx).
PR values are raw percentages (e.g. 53.08 = 53.08%).
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

from arena_buddy.scraper.lolalytics import (
    ItemStat, AugmentStat, ScrapeResult,
)

logger = logging.getLogger(__name__)


_ANVILS = {"Stat Bonus","Prismatic Item","Legendary Marksman Item","Legendary Mage Item",
    "Legendary Assassin Item","Legendary Fighter Item","Legendary Tank Item",
    "Legendary Support Item","Juice of Power","Gain Stat Anvil",
    "Gain a Prismatic Stat Anvil","Level Augments","Gain an Augment slot",
    "Gold Stat Anvil Voucher","Silver Stat Anvil Voucher","Juice of Vitality",
    "Juice of Haste","Juice of Power","Juice of Speed","Juice of Tenacity"}

_CHAMPION_URL_MAP = {"Nunu & Willump":"nunu","Wukong":"monkeyking"}

def _slug(n: str) -> str:
    if n in _CHAMPION_URL_MAP: return _CHAMPION_URL_MAP[n]
    n = n.lower(); n = re.sub(r"['']","",n); n = re.sub(r"\.+","",n)
    return re.sub(r"\s+","",n)

def _find_browser() -> str|None:
    import glob
    cs = ["/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell"]
    cs += glob.glob(os.path.expanduser("~/.playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    for c in cs:
        if os.path.exists(c): return c
    return None


def scrape_and_store(
    conn: Any,
    champion_id: int,
    champion_key: str,
    patch: str,
    *,
    headless: bool = True,
) -> ScrapeResult:
    """Scrape a champion and store results in the database.

    Full pipeline: browser scrape → name matching → DB upsert.

    Args:
        conn: An open sqlite3.Connection.
        champion_id: Database ID of the champion.
        champion_key: Data Dragon champion key (e.g. "Lucian").
        patch: Patch version string (e.g. "16.11").
        headless: Run browser in headless mode.

    Returns:
        The ScrapeResult with DB IDs populated.
    """
    from arena_buddy.scraper.name_matcher import match_items, match_augments

    # Scrape
    result = scrape_champion(champion_key, patch, headless=headless)

    # Match item names to DB IDs
    item_names = [it.name for it in result.items]
    item_map = match_items(conn, item_names)
    for it in result.items:
        it.id = item_map.get(it.name)

    # Match augment names to DB IDs + rarity
    aug_names = [a.name for a in result.augments]
    aug_map = match_augments(conn, aug_names)
    for a in result.augments:
        db_id, db_rarity = aug_map.get(a.name, (None, None))
        a.id = db_id
        if db_rarity is not None:
            a.rarity = db_rarity

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

    # Store in DB
    from arena_buddy.scraper.lolalytics import store_champion_stats
    store_champion_stats(conn, champion_id, patch_id, result)

    matched_items = sum(1 for it in result.items if it.id is not None)
    matched_augs = sum(1 for a in result.augments if a.id is not None)
    logger.info(
        "Stored %s: %d/%d items, %d/%d augments",
        champion_key, matched_items, len(result.items),
        matched_augs, len(result.augments),
    )
    return result


def scrape_champion(champion_key: str, patch: str, *, headless: bool = True) -> ScrapeResult:
    """Scrape a single champion from LoLalytics (raw, no DB matching)."""
    from playwright.sync_api import sync_playwright
    url = f"https://lolalytics.com/lol/{_slug(champion_key)}/arena/build/?patch={patch}"
    logger.info("Scraping %s", url)
    bexe = _find_browser()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=bexe, headless=headless,
            args=["--no-sandbox","--disable-gpu","--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width":1920,"height":4000})
        try:
            page.goto(url, wait_until="load", timeout=30000); time.sleep(3)
            try: page.click('button:has-text("Accept")', timeout=3000)
            except: pass
            for _ in range(25):
                if page.evaluate("() => document.querySelectorAll('div.cursor-grab').length") >= 10: break
                time.sleep(1)
            items = _items(page)
            augments = _augments(page)
        finally: browser.close()

    logger.info("%s: %d items, %d augments", champion_key, len(items), len(augments))
    return ScrapeResult(items=items, augments=augments)


def _items(page) -> list[ItemStat]:
    """Extract items from item sections. Uses precise class selectors."""
    raw = page.evaluate("""() => {
        const result = [];
        const scrolls = document.querySelectorAll('div.cursor-grab');

        scrolls.forEach(scroll => {
            // Determine if this is an item section
            let label = '';
            let el = scroll.previousElementSibling;
            for (let i = 0; i < 3 && el; i++) {
                const t = el.textContent.trim();
                if (t.length > 2 && t.length < 60) { label = t; break; }
                el = el.previousElementSibling;
            }

            const isItem = ['Starting','Prismatic','Popular','Winning','All'].some(s => label.includes(s));
            if (!isItem) return;

            const cards = scroll.querySelectorAll('div.flex.gap-\\\\[6px\\\\] > div');
            cards.forEach(card => {
                const img = card.querySelector('img');
                if (!img || !img.alt) return;
                const name = img.alt.trim();
                if (!name || name.length < 2 || name.length > 60) return;

                // Check if this is an anvil item
                const anvilNames = ['Stat Bonus','Prismatic Item','Legendary Marksman Item',
                    'Legendary Mage Item','Legendary Assassin Item','Legendary Fighter Item',
                    'Legendary Tank Item','Legendary Support Item','Juice of Power',
                    'Gain Stat Anvil','Gain a Prismatic Stat Anvil','Juice of Vitality',
                    'Juice of Haste','Juice of Tenacity','Juice of Speed'];
                if (anvilNames.includes(name)) return;

                // WR: div.my-1 WITHOUT text-green-500 or text-[#939bf6] class
                const wrDiv = card.querySelector('div.my-1:not([class*=\"green\"]):not([class*=\"939bf6\"]):not([class*=\"bbbbbb\"])');
                if (!wrDiv) return;
                const wrText = wrDiv.textContent.trim();
                if (wrText === 'xx.xx' || !/^\\d+(\\.\\d+)?$/.test(wrText)) return;
                const wr = parseFloat(wrText) / 100;

                // PR: div with text-[#939bf6]
                const prDiv = card.querySelector('div[class*=\"939bf6\"]');
                let pr = 0;
                if (prDiv) {
                    const t = prDiv.textContent.trim();
                    pr = parseFloat(t) / 100 || 0;
                }

                // Games: div with text-[#bbbbbb] (the one with 9px font)
                const gDiv = card.querySelector('div[class*=\"bbbbbb\"]');
                let games = 0;
                if (gDiv) {
                    const t = gDiv.textContent.trim().replace(/,/g, '');
                    games = parseInt(t) || 0;
                }

                if (wr > 0 && games >= 10) result.push({name, wr, pr, games});
            });
        });
        return result;
    }""")

    seen = {}
    for d in raw:
        n = d["name"]
        if n not in seen or d["wr"] > seen[n].win_rate:
            seen[n] = ItemStat(id=None, name=n, win_rate=d["wr"],
                pick_rate=d["pr"], games_played=d["games"], rank=0)
    result = sorted(seen.values(), key=lambda x: x.win_rate, reverse=True)
    for i, it in enumerate(result, 1): it.rank = i
    return result


def _augments(page) -> list[AugmentStat]:
    """Extract augments by cycling tier tabs. Uses precise class selectors."""
    rarity_map = {}
    all_data = {}

    for label, rkey in [("Prismatic","prismatic"),("Gold","gold"),("Silver","silver")]:
        try:
            page.click(f'div:has-text("{label} Augments")', timeout=3000)
            time.sleep(1.5)
        except: continue

        tab = page.evaluate("""() => {
            const result = [];
            const scrolls = document.querySelectorAll('div.cursor-grab');
            scrolls.forEach(scroll => {
                let label = '';
                let el = scroll.previousElementSibling;
                for (let i = 0; i < 3 && el; i++) {
                    const t = el.textContent.trim();
                    if (t.length > 2 && t.length < 60) { label = t; break; }
                    el = el.previousElementSibling;
                }
                if (!label.includes('Augment')) return;

                const cards = scroll.querySelectorAll('div.flex.gap-\\\\[6px\\\\] > div');
                cards.forEach(card => {
                    const img = card.querySelector('img');
                    if (!img || !img.alt) return;
                    const name = img.alt.trim();
                    if (!name || name.length < 2 || name.length > 60) return;

                    // Augments have text-green-500 WR div (xx.xx)
                    const wrDiv = card.querySelector('div[class*=\"green-500\"]');
                    if (!wrDiv) return;
                    const wrText = wrDiv.textContent.trim();
                    if (wrText !== 'xx.xx') return;  // Only augments have xx.xx

                    const anvilNames = ['Stat Bonus','Prismatic Item','Legendary Marksman Item',
                        'Legendary Mage Item','Legendary Assassin Item','Legendary Fighter Item',
                        'Legendary Tank Item','Legendary Support Item','Juice of Power',
                        'Gain Stat Anvil','Gain a Prismatic Stat Anvil','Level Augments',
                        'Gain an Augment slot','Gold Stat Anvil Voucher','Juice of Vitality',
                        'Juice of Haste','Juice of Tenacity','Juice of Speed'];
                    if (anvilNames.includes(name)) return;

                    const prDiv = card.querySelector('div[class*=\"939bf6\"]');
                    let pr = 0;
                    if (prDiv) pr = parseFloat(prDiv.textContent.trim()) / 100 || 0;

                    const gDiv = card.querySelector('div[class*=\"bbbbbb\"]');
                    let games = 0;
                    if (gDiv) games = parseInt(gDiv.textContent.trim().replace(/,/g,'')) || 0;

                    if (games >= 5) result.push({name, pr, games});
                });
            });
            return result;
        }""")

        for d in tab:
            rarity_map[d["name"]] = rkey
            if d["name"] not in all_data or d["pr"] > all_data[d["name"]]["pr"]:
                all_data[d["name"]] = d

    augs = []
    for name, data in all_data.items():
        augs.append(AugmentStat(id=None, name=name, rarity=rarity_map.get(name,"silver"),
            win_rate=0.0, pick_rate=data["pr"], games_played=data["games"], rank=0))

    counters = {}
    augs.sort(key=lambda a: a.pick_rate, reverse=True)
    for a in augs:
        rk = str(a.rarity); counters[rk] = counters.get(rk,0) + 1; a.rank = counters[rk]
    return augs
