"""FastAPI application factory for Arena Buddy.

Creates and configures the FastAPI app, sets up database connection,
mounts API routes, and serves static files (HTML/CSS/JS).
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from arena_buddy import __version__
from arena_buddy.db.connection import init_database
from arena_buddy.db.seed import seed_all
from arena_buddy.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initializes DB, orchestrator, and WS on startup."""
    db_path = app.state.db_path
    init_database(db_path)

    # Seed data (idempotent — safe to call every startup)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        seed_all(conn)
    finally:
        conn.close()

    # Initialize WebSocket manager
    from arena_buddy.web.websocket import WebSocketManager
    ws_manager = WebSocketManager()
    app.state.ws_manager = ws_manager

    # Initialize GameOrchestrator (auto-detection disabled if no League client)
    from arena_buddy.core.orchestrator import GameOrchestrator, GameEventType
    orchestrator = GameOrchestrator(db_path=str(db_path))
    app.state.orchestrator = orchestrator

    # Wire match capture service to game-end events
    from arena_buddy.core.match_capture_service import MatchCaptureService
    capture_service = MatchCaptureService(db_path=str(db_path))
    orchestrator.on_event(capture_service.on_game_end)
    app.state.capture_service = capture_service

    # Wire orchestrator events → WebSocket broadcasts
    async def broadcast_to_ws(event):
        await ws_manager.broadcast(event.full_details)

    orchestrator.on_event(broadcast_to_ws)

    # Start the orchestrator in the background (silently fails if no League)
    import asyncio
    poll_task = asyncio.create_task(orchestrator.start())

    # Patch checker: periodically checks for new Data Dragon patch
    async def _patch_checker():
        """Check for new patches every 6 hours while the app runs."""
        while True:
            await asyncio.sleep(21600)  # 6 hours
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        "https://ddragon.leagueoflegends.com/api/versions.json"
                    )
                    resp.raise_for_status()
                    versions = resp.json()
                    latest = ".".join(versions[0].split(".")[:2]) if versions else None

                if latest:
                    conn2 = sqlite3.connect(str(db_path))
                    try:
                        current = conn2.execute(
                            "SELECT version FROM patches WHERE is_current = 1"
                        ).fetchone()
                        current_version = current[0] if current else None
                        if current_version and latest != current_version:
                            import logging
                            logging.getLogger(__name__).info(
                                "New patch detected: %s → %s", current_version, latest
                            )
                            # Mark old patch as not current, insert new
                            conn2.execute(
                                "UPDATE patches SET is_current = 0 WHERE is_current = 1"
                            )
                            conn2.execute(
                                "INSERT OR IGNORE INTO patches (version, is_current) VALUES (?, 1)",
                                (latest,),
                            )
                            conn2.commit()
                    finally:
                        conn2.close()
            except Exception:
                pass  # Silently ignore errors in background checker

    asyncio.create_task(_patch_checker())

    yield  # App is running

    # Cleanup
    await orchestrator.stop()
    try:
        poll_task.cancel()
        await poll_task
    except (asyncio.CancelledError, Exception):
        pass


def create_app(db_path: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to SQLite database.  If None, uses default from config.

    Returns:
        A fully configured FastAPI app ready for ``uvicorn.run()``.
    """
    if db_path is None:
        from arena_buddy.config import get_db_path
        db_path = get_db_path()

    # Resolve the static files directory relative to this module
    static_dir = Path(__file__).parent / "static"

    app = FastAPI(
        title="Arena Buddy",
        description="LoL Arena companion — item/augment recommendations",
        version=__version__,
        lifespan=lifespan,
    )

    # Store db_path in app state for routes to access
    app.state.db_path = Path(db_path)

    # Mount static files (CSS, JS, images)
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Register API routes
    app.include_router(router, prefix="/api")

    # Serve cached icons (follow_symlink=True because cache subdirs
    # may be symlinks on some setups)
    from arena_buddy.config import get_cache_dir
    cache_dir = get_cache_dir()
    if cache_dir.exists():
        app.mount(
            "/icons",
            StaticFiles(directory=str(cache_dir), follow_symlink=True),
            name="icons",
        )

    # Serve index.html at root
    @app.get("/")
    async def index():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"status": "ok", "message": "Arena Buddy API — see /docs for API reference"}

    return app
