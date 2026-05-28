"""Data import module for Arena Buddy.

Parses Data Dragon and CommunityDragon JSON files and imports
champions, items, and augments into the SQLite database.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def import_champions(conn: sqlite3.Connection, champions_json_path: str | Path) -> int:
    """Parse Data Dragon champions JSON and insert all champions.

    Uses ``INSERT OR IGNORE`` so the call is idempotent — running it
    multiple times with the same data will not duplicate rows.

    Args:
        conn: An open :class:`sqlite3.Connection`.
        champions_json_path: Path to a Data Dragon champions JSON file
            (e.g., ``champion.json`` from ddragon).

    Returns:
        Number of champion rows *attempted* (may be higher than the
        number actually inserted on re-runs).

    Raises:
        FileNotFoundError: If *champions_json_path* does not exist.
        ValueError: If the file contains malformed JSON or the
            expected ``data`` key is missing.
    """
    path = Path(champions_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Champions data file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Malformed JSON in champions file {path}: {exc}"
        ) from exc

    if "data" not in data:
        raise ValueError(
            f"Unexpected JSON structure in champions file {path}: "
            f"missing 'data' key"
        )

    champions_data = data["data"]
    rows: list[tuple[int, str, str, str]] = []
    for _champ_id_str, champ in champions_data.items():
        rows.append((
            int(champ["key"]),          # id  — numeric key (e.g. 266)
            champ["id"],                # key — string id  (e.g. "Aatrox")
            champ["name"],              # name
            champ["image"]["full"],     # icon_filename
        ))

    conn.executemany(
        "INSERT OR IGNORE INTO champions (id, key, name, icon_filename) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def import_items(conn: sqlite3.Connection, items_json_path: str | Path) -> int:
    """Parse Data Dragon items JSON and insert all items.

    Uses ``INSERT OR IIGNORE`` — idempotent.

    Args:
        conn: An open :class:`sqlite3.Connection`.
        items_json_path: Path to a Data Dragon items JSON file
            (e.g., ``item.json`` from ddragon).

    Returns:
        Number of item rows *attempted*.

    Raises:
        FileNotFoundError: If *items_json_path* does not exist.
        ValueError: If the file contains malformed JSON or the
            expected ``data`` key is missing.
    """
    path = Path(items_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Items data file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Malformed JSON in items file {path}: {exc}"
        ) from exc

    if "data" not in data:
        raise ValueError(
            f"Unexpected JSON structure in items file {path}: "
            f"missing 'data' key"
        )

    items_data = data["data"]
    rows: list[tuple[int, str, str, int, str]] = []
    for item_id_str, item in items_data.items():
        gold = item.get("gold", {})
        desc = item.get("plaintext") or item.get("description") or ""
        rows.append((
            int(item_id_str),           # id
            item["name"],               # name
            item["image"]["full"],      # icon_filename
            gold.get("total", 0),       # gold_cost
            desc,                       # description
        ))

    conn.executemany(
        "INSERT OR IGNORE INTO items (id, name, icon_filename, gold_cost, description) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def import_augments(conn: sqlite3.Connection, augments_json_path: str | Path) -> int:
    """Parse CommunityDragon augments JSON and insert all augments.

    Augments are assigned auto-increment IDs starting from **1000**.
    To keep IDs deterministic (and therefore idempotent with
    ``INSERT OR IGNORE``) the augment list is sorted alphabetically
    by ``apiName`` before IDs are assigned.

    Args:
        conn: An open :class:`sqlite3.Connection`.
        augments_json_path: Path to a CommunityDragon augments JSON
            file (e.g., from the ``cdragon`` / arena plugin).

    Returns:
        Number of augment rows *attempted*.

    Raises:
        FileNotFoundError: If *augments_json_path* does not exist.
        ValueError: If the file contains malformed JSON or the
            expected ``augments`` key is missing.
    """
    path = Path(augments_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Augments data file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Malformed JSON in augments file {path}: {exc}"
        ) from exc

    if "augments" not in data:
        raise ValueError(
            f"Unexpected JSON structure in augments file {path}: "
            f"missing 'augments' key"
        )

    augments_list = list(data["augments"])
    # Sort deterministically so IDs are stable across runs
    augments_list.sort(key=lambda a: a.get("apiName", ""))

    rows: list[tuple[int, str, str, int, str, str]] = []
    next_id = 1000
    for aug in augments_list:
        icon = aug.get("iconSmall") or ""
        icon_filename = os.path.basename(icon) if icon else ""
        rows.append((
            next_id,                    # id (auto-increment from 1000)
            aug["apiName"],             # api_name
            aug["name"],                # name
            aug.get("rarity", 0),       # rarity
            aug.get("desc", ""),        # description
            icon_filename,              # icon_filename
        ))
        next_id += 1

    conn.executemany(
        "INSERT OR IGNORE INTO augments "
        "(id, api_name, name, rarity, description, icon_filename) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def import_all(
    conn: sqlite3.Connection,
    champions_path: str | Path,
    items_path: str | Path,
    augments_path: str | Path,
) -> dict[str, int]:
    """Run all three importers in a single call.

    Args:
        conn: An open :class:`sqlite3.Connection`.
        champions_path: Path to Data Dragon champions JSON.
        items_path: Path to Data Dragon items JSON.
        augments_path: Path to CommunityDragon augments JSON.

    Returns:
        A dict mapping table names to attempted row counts:
        ``{"champions": N, "items": N, "augments": N}``.

    Raises:
        FileNotFoundError: If any of the paths do not exist.
        ValueError: If any of the files contain malformed JSON.
    """
    return {
        "champions": import_champions(conn, champions_path),
        "items": import_items(conn, items_path),
        "augments": import_augments(conn, augments_path),
    }
