"""API routes for Arena Buddy.

Serves champion recommendations, match history, and stats.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from arena_buddy.db import queries
from arena_buddy.db.connection import get_connection

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_db_path(request: Request) -> Path:
    """Extract db_path from app state (set during lifespan)."""
    return request.app.state.db_path


def _connect(request: Request) -> sqlite3.Connection:
    """Get an open connection with row_factory set."""
    db_path = _get_db_path(request)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health")
async def health():
    """Health check — returns app status and version."""
    from arena_buddy import __version__
    return {"status": "ok", "version": __version__}


@router.get("/champions")
async def list_champions(request: Request):
    """Return all champions in the database."""
    conn = _connect(request)
    try:
        return queries.get_all_champions(conn)
    finally:
        conn.close()


@router.get("/champions/{key}/items")
async def champion_recommendations(request: Request, key: str):
    """Return item and augment recommendations for a champion.

    Response shape:
        {
            "champion": {...},
            "patch": "16.11",
            "last_updated": "2026-05-28T12:00:00",
            "items": [{...}, ...],
            "augments": {"prismatic": [...], "gold": [...], "silver": [...]}
        }
    """
    conn = _connect(request)
    try:
        champ = queries.get_champion_by_key(conn, key)
        if champ is None:
            raise HTTPException(status_code=404, detail=f"Champion '{key}' not found")

        patch = queries.get_current_patch(conn)
        patch_version = patch["version"] if patch else "unknown"
        last_updated = patch["scraped_at"] if patch and patch["scraped_at"] else None

        patch_id = patch["id"] if patch else 1
        items = queries.get_items_for_champion(conn, champ["id"], patch_id)
        augments = queries.get_augments_for_champion(conn, champ["id"], patch_id)

        return {
            "champion": champ,
            "patch": patch_version,
            "last_updated": str(last_updated) if last_updated else None,
            "items": items,
            "augments": augments,
        }
    finally:
        conn.close()


@router.get("/stats/summary")
async def stats_summary(request: Request):
    """Return a summary of the current stats database."""
    conn = _connect(request)
    try:
        patch = queries.get_current_patch(conn)
        champions = queries.get_all_champions(conn)

        return {
            "patch": patch["version"] if patch else "unknown",
            "last_updated": str(patch["scraped_at"]) if patch and patch["scraped_at"] else None,
            "champions_covered": len(champions),
        }
    finally:
        conn.close()
