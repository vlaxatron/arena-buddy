"""Name matcher — maps scraped LoLalytics item/augment names to DB IDs.

LoLalytics names may differ from CommunityDragon names. This module
fuzzy-matches scraped names to the items/augments tables.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def match_items(
    conn: sqlite3.Connection,
    scraped_names: list[str],
) -> dict[str, int | None]:
    """Map scraped item names to database item IDs.

    Uses exact match first, then normalized comparison (lowercase, strip
    punctuation, collapse spaces).

    Returns a dict mapping each scraped name to its item ID (or None).
    """
    # Build lookup: normalized name → id
    db_items = conn.execute("SELECT id, name FROM items").fetchall()
    exact_map: dict[str, int] = {}
    norm_map: dict[str, int] = {}

    for row in db_items:
        db_name = row["name"]
        exact_map[db_name.lower()] = row["id"]
        norm_map[_normalize(db_name)] = row["id"]

    result: dict[str, int | None] = {}
    for name in scraped_names:
        # Try exact match
        item_id = exact_map.get(name.lower())
        if item_id is not None:
            result[name] = item_id
            continue

        # Try normalized match
        norm = _normalize(name)
        item_id = norm_map.get(norm)
        if item_id is not None:
            result[name] = item_id
            continue

        # Try partial/word match
        item_id = _partial_match(name, exact_map)
        if item_id is not None:
            result[name] = item_id
            continue

        result[name] = None

    matched = sum(1 for v in result.values() if v is not None)
    logger.info("Matched %d/%d items to DB IDs", matched, len(result))
    return result


def match_augments(
    conn: sqlite3.Connection,
    scraped_names: list[str],
) -> dict[str, tuple[int | None, int | None]]:
    """Map scraped augment names to database (augment_id, rarity).

    Uses exact match on name/api_name, then normalized comparison.
    For duplicates (same name, different rarity), prefers the entry
    with matching rarity if known, otherwise picks lowest ID.

    Returns a dict mapping each scraped name to (augment_id, rarity)
    or (None, None).
    """
    db_augs = conn.execute(
        "SELECT id, api_name, name, rarity FROM augments WHERE rarity IN (0,1,2)"
    ).fetchall()

    exact_map: dict[str, list[tuple[int, int]]] = {}  # name → [(id, rarity)]
    norm_map: dict[str, list[tuple[int, int]]] = {}

    for row in db_augs:
        db_name = row["name"]
        aid, r = row["id"], row["rarity"]

        key = db_name.lower()
        if key not in exact_map:
            exact_map[key] = []
        exact_map[key].append((aid, r))

        nkey = _normalize(db_name)
        if nkey not in norm_map:
            norm_map[nkey] = []
        norm_map[nkey].append((aid, r))

        # Also index by api_name
        api_key = row["api_name"].lower()
        if api_key not in exact_map:
            exact_map[api_key] = []
        exact_map[api_key].append((aid, r))

    def _pick(candidates: list[tuple[int, int]]) -> tuple[int | None, int | None]:
        if not candidates:
            return (None, None)
        # Pick lowest ID (canonical)
        candidates.sort(key=lambda x: x[0])
        return (candidates[0][0], candidates[0][1])

    result: dict[str, tuple[int | None, int | None]] = {}
    for name in scraped_names:
        key = name.lower()
        candidates = exact_map.get(key)
        if candidates:
            result[name] = _pick(candidates)
            continue

        nkey = _normalize(name)
        candidates = norm_map.get(nkey)
        if candidates:
            result[name] = _pick(candidates)
            continue

        # Try fuzzy: check if name contains or is contained by DB names
        for db_name_key, cands in exact_map.items():
            if name.lower() in db_name_key or db_name_key in name.lower():
                result[name] = _pick(cands)
                break
        else:
            result[name] = (None, None)

    matched = sum(1 for v in result.values() if v[0] is not None)
    logger.info("Matched %d/%d augments to DB IDs", matched, len(result))
    return result


def _normalize(s: str) -> str:
    """Normalize a name for fuzzy comparison."""
    s = s.lower()
    s = re.sub(r"['']", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s


def _partial_match(name: str, exact_map: dict[str, int]) -> int | None:
    """Try partial word matching."""
    name_lower = name.lower()
    words = set(name_lower.split())

    for db_name, db_id in exact_map.items():
        db_words = set(db_name.split())
        # If there's significant word overlap
        common = words & db_words
        if len(common) >= min(2, len(words), len(db_words)):
            return db_id

    return None
