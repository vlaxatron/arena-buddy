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
    """Application lifespan — initializes DB and seed data on startup."""
    db_path = app.state.db_path
    init_database(db_path)

    # Seed data (idempotent — safe to call every startup)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        seed_all(conn)
    finally:
        conn.close()

    yield  # App is running
    # Cleanup (if needed) goes here


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

    # Serve cached icons
    from arena_buddy.config import get_cache_dir
    cache_dir = get_cache_dir()
    if cache_dir.exists():
        app.mount("/icons", StaticFiles(directory=str(cache_dir)), name="icons")

    # Serve index.html at root
    @app.get("/")
    async def index():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"status": "ok", "message": "Arena Buddy API — see /docs for API reference"}

    return app
