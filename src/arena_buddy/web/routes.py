"""API routes for Arena Buddy.

Serves champion recommendations, match history, and stats.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import json
import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket
from starlette.websockets import WebSocketDisconnect

from arena_buddy.db import queries
from arena_buddy.db.connection import get_connection

router = APIRouter()
logger = logging.getLogger(__name__)


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
            "prismatic_items": [{...}, ...],
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
        all_items = queries.get_items_for_champion(conn, champ["id"], patch_id)
        augments = queries.get_augments_for_champion(conn, champ["id"], patch_id)

        # Split items: prismatic vs regular
        prismatic_items = [i for i in all_items if i.get("is_prismatic")]
        regular_items = [i for i in all_items if not i.get("is_prismatic")]

        # --- Lazily ensure icons exist for this champion's data ---
        item_ids = [it["id"] for it in all_items]
        augment_api_names: list[str] = []
        for tier_augs in augments.values():
            for a in tier_augs:
                api_name = a.get("api_name", "")
                if api_name:
                    augment_api_names.append(api_name)

        try:
            from arena_buddy.assets.icons import ensure_icons_for_champion
            ensure_icons_for_champion(
                champion_key=key,
                champion_icon=champ["icon_filename"],
                item_ids=item_ids,
                augment_api_names=augment_api_names,
            )
        except Exception:
            # Never let icon download failures break the API response
            pass

        return {
            "champion": champ,
            "patch": patch_version,
            "last_updated": str(last_updated) if last_updated else None,
            "items": regular_items,
            "prismatic_items": prismatic_items,
            "augments": augments,
            "fetching": False,
        }

    finally:
        conn.close()

    # --- AFTER closing conn: if no stats, trigger background scrape ---
    if (
        not all_items
        and not any(augments.get(tier, []) for tier in ("prismatic", "gold", "silver"))
    ):
        _trigger_single_champion_scrape(key, patch_version)


# ---------------------------------------------------------------------------
# Background single-champion scrape helper
# ---------------------------------------------------------------------------

def _trigger_single_champion_scrape(champion_key: str, patch: str) -> None:
    """Fire-and-forget a scrape for a single champion in a daemon thread.

    Used when a user selects a champion that hasn't been scraped yet.
    """
    import asyncio
    import threading

    def _run():
        from arena_buddy.scraper.qwik_scraper import scrape_and_store_qwik
        from arena_buddy.config import get_db_path
        import sqlite3
        import logging
        logger = logging.getLogger(__name__)

        db_path = get_db_path()
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                # Look up champion_id
                row = conn.execute(
                    "SELECT id FROM champions WHERE key = ?", (champion_key,)
                ).fetchone()
                if not row:
                    return
                champion_id = row[0]

                scrape_and_store_qwik(conn, champion_id, champion_key, patch)
                logger.info(
                    "Auto-scraped %s via Qwik", champion_key,
                )
            finally:
                conn.close()
        except Exception:
            logger.exception("Auto-scrape failed for %s", champion_key)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


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


@router.get("/champions/{key}/recent-matches")
async def champion_recent_matches(request: Request, key: str, limit: int = 5):
    """Return the last N matches for a champion with item/augment summaries.

    Returns a compact list suitable for the champion header match strip.

    Query params:
        limit: Maximum matches to return (default 5, max 8).

    Returns:
        ``{"matches": [{...}, ...]}``
    """
    limit = min(limit, 8)
    conn = _connect(request)
    try:
        champ = queries.get_champion_by_key(conn, key)
        if champ is None:
            raise HTTPException(status_code=404, detail=f"Champion '{key}' not found")

        matches = conn.execute(
            """
            SELECT m.game_id, m.win, m.placement, m.kills, m.deaths, m.assists,
                   m.match_timestamp, m.champion_key
            FROM matches m
            WHERE m.champion_id = ?
            ORDER BY m.match_timestamp DESC
            LIMIT ?
            """,
            (champ["id"], limit),
        ).fetchall()

        result = []
        for m in matches:
            md = dict(m)
            # Get items for this match
            items = conn.execute(
                """
                SELECT i.name, i.icon_filename, mi.slot
                FROM match_items mi
                JOIN items i ON mi.item_id = i.id
                WHERE mi.game_id = ?
                ORDER BY mi.slot
                """,
                (md["game_id"],),
            ).fetchall()
            md["items"] = [dict(it) for it in items]

            # Get augments
            augments = conn.execute(
                """
                SELECT a.name, a.icon_filename, a.rarity, ma.slot
                FROM match_augments ma
                JOIN augments a ON ma.augment_id = a.id
                WHERE ma.game_id = ?
                ORDER BY ma.slot
                """,
                (md["game_id"],),
            ).fetchall()
            md["augments"] = [dict(a) for a in augments]

            result.append(md)

        return {"champion": champ, "matches": result}
    finally:
        conn.close()


@router.get("/champions/search")
async def search_champions(request: Request, q: str = ""):
    """Search champions by name or key (case-insensitive, partial match).

    Query params:
        q: Search string (matched against champion name and key).

    Returns:
        List of matching champion dicts. Empty list if q is empty.
    """
    if not q.strip():
        return []
    conn = _connect(request)
    try:
        return queries.search_champions(conn, q.strip())
    finally:
        conn.close()


@router.get("/matches")
async def list_matches(
    request: Request,
    champion: str | None = None,
    placement: int | None = None,
    limit: int = 20,
    offset: int = 0,
):
    """List matches with optional filters and pagination.

    Query params:
        champion: Filter by champion key (e.g., "Lucian").
        placement: Filter by placement (1-4).
        limit: Maximum matches to return (default 20, max 100).
        offset: Number of matches to skip (default 0).

    Returns:
        ``{"matches": [...], "total": N, "limit": N, "offset": N, "stats": {...}}``
    """
    limit = min(limit, 100)
    limit = max(limit, 1)

    conn = _connect(request)
    try:
        matches = queries.list_matches(conn, champion_key=champion, placement=placement, limit=limit, offset=offset)
        total = queries.count_matches(conn, champion_key=champion, placement=placement)
        stats = queries.get_match_stats(conn, champion_key=champion)

        return {
            "matches": matches,
            "total": total,
            "limit": limit,
            "offset": offset,
            "stats": stats,
        }
    finally:
        conn.close()


@router.get("/matches/{match_id}")
async def get_match(request: Request, match_id: str):
    """Return full match detail with participants, items, and augments.

    Path params:
        match_id: The game_id of the match.

    Returns:
        Full match detail dict with participants array.
    """
    conn = _connect(request)
    try:
        detail = queries.get_match_detail(conn, match_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Match '{match_id}' not found")
        return detail
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Icon management
# ---------------------------------------------------------------------------

@router.post("/icons/ensure/{champion_key}")
async def ensure_champion_icons(request: Request, champion_key: str):
    """Trigger lazy icon download for a champion.

    Downloads any missing champion, item, and augment icons for the
    specified champion.  Safe to call repeatedly — already-cached
    icons are skipped.

    Returns:
        ``{"status": "ok", "downloaded": {...}, "champion": "Lucian"}``
    """
    conn = _connect(request)
    try:
        champ = queries.get_champion_by_key(conn, champion_key)
        if champ is None:
            raise HTTPException(status_code=404, detail=f"Champion '{champion_key}' not found")

        patch = queries.get_current_patch(conn)
        patch_id = patch["id"] if patch else 1
        all_items = queries.get_items_for_champion(conn, champ["id"], patch_id)
        augments = queries.get_augments_for_champion(conn, champ["id"], patch_id)

        item_ids = [it["id"] for it in all_items]
        augment_api_names: list[str] = []
        for tier_augs in augments.values():
            for a in tier_augs:
                api_name = a.get("api_name", "")
                if api_name:
                    augment_api_names.append(api_name)

        from arena_buddy.assets.icons import ensure_icons_for_champion

        downloaded = ensure_icons_for_champion(
            champion_key=champion_key,
            champion_icon=champ["icon_filename"],
            item_ids=item_ids,
            augment_api_names=augment_api_names,
        )

        return {
            "status": "ok",
            "downloaded": downloaded,
            "champion": champion_key,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# WebSocket — Real-time game state
# ---------------------------------------------------------------------------

@router.websocket("/ws/game-state")
async def websocket_game_state(websocket: WebSocket):
    """WebSocket endpoint for real-time game state broadcasts.

    Clients receive JSON messages with game state events:
    ``{"type": "GAME_START", "champion": "Lucian", ...}``

    An initial ``{"type": "STATUS", "message": "Connected"}`` is sent
    on connection.
    """
    from arena_buddy.web.websocket import WebSocketManager

    # Get or create the WebSocket manager from app state
    app = websocket.scope.get("app")
    if app is None:
        return

    if not hasattr(app.state, "ws_manager"):
        app.state.ws_manager = WebSocketManager()

    manager: WebSocketManager = app.state.ws_manager

    await manager.connect(websocket)
    try:
        # Send initial status
        await websocket.send_json({
            "type": "STATUS",
            "message": "Connected to Arena Buddy",
        })

        # Keep the connection alive — listen for client messages
        while True:
            try:
                data = await websocket.receive_text()
                # Client can send ping/heartbeat
                if data == "ping":
                    await websocket.send_json({"type": "PONG"})
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception("WebSocket receive error")
                break
    finally:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Stats scraping — trigger LoLalytics refresh
# ---------------------------------------------------------------------------

@router.post("/stats/scrape")
async def trigger_scrape(request: Request):
    """Trigger a full LoLalytics scrape for all champions.

    Runs synchronously (may take several minutes).  Returns progress
    information as the scrape proceeds.

    Returns:
        ``{"status": "started", "champions": N, ...}``
    """
    import logging
    import time

    conn = _connect(request)
    try:
        champions = queries.get_all_champions(conn)
        current_patch = queries.get_current_patch(conn)
        patch_version = current_patch["version"] if current_patch else "16.11"

        # Run scrape in a thread to not block the event loop
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        def _run_scrape():
            from arena_buddy.scraper.qwik_scraper import scrape_all_champions_qwik
            import sqlite3 as _sqlite3

            # Make a fresh connection for the scraper thread
            db_path = request.app.state.db_path
            scrape_conn = _sqlite3.connect(str(db_path))
            scrape_conn.execute("PRAGMA foreign_keys = ON")
            try:
                scrape_all_champions_qwik(
                    conn=scrape_conn,
                    champions=[dict(c) for c in champions],
                    patch=patch_version,
                    rate_limit=3.0,
                )
                scrape_conn.commit()
            finally:
                scrape_conn.close()

        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            loop.run_in_executor(pool, _run_scrape)

        return {
            "status": "started",
            "champions": len(champions),
            "patch": patch_version,
            "message": f"Scraping {len(champions)} champions at patch {patch_version}",
        }

    finally:
        conn.close()


@router.get("/stats/check-patch")
async def check_patch(request: Request):
    """Check if a newer Data Dragon patch is available.

    Compares the current stored patch against the latest Data Dragon
    version.  Returns whether an update is needed.

    Returns:
        ``{"current_patch": "16.11", "latest_patch": "16.12", "update_needed": true}``
    """
    import httpx

    conn = _connect(request)
    try:
        current_patch = queries.get_current_patch(conn)
        current_version = current_patch["version"] if current_patch else None

        # Fetch latest patch from Data Dragon
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://ddragon.leagueoflegends.com/api/versions.json"
                )
                resp.raise_for_status()
                versions = resp.json()
                latest = versions[0] if versions else None
                # versions are like "16.11.1" — trim to "16.11"
                latest_patch = ".".join(latest.split(".")[:2]) if latest else None
        except Exception:
            latest_patch = None

        update_needed = (
            current_version is not None
            and latest_patch is not None
            and current_version != latest_patch
        )

        return {
            "current_patch": current_version,
            "latest_patch": latest_patch,
            "update_needed": update_needed,
        }
    finally:
        conn.close()
