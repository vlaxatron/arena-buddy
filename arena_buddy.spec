# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Arena Buddy — Windows desktop application.

Builds a single .exe that bundles Python, FastAPI, and the web frontend.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["src/arena_buddy/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        # Static web assets (HTML, CSS, JS)
        ("src/arena_buddy/web/static", "arena_buddy/web/static"),
    ],
    hiddenimports=[
        # FastAPI / uvicorn internals
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.logging",
        "fastapi",
        "starlette",
        # Database
        "sqlite3",
        # Scraping
        "httpx",
        "beautifulsoup4",
        # WebView
        "webview",
        # Arena Buddy internals
        "arena_buddy",
        "arena_buddy.config",
        "arena_buddy.db",
        "arena_buddy.db.connection",
        "arena_buddy.db.schema",
        "arena_buddy.db.seed",
        "arena_buddy.db.queries",
        "arena_buddy.db.personal_stats",
        "arena_buddy.db.importer",
        "arena_buddy.web",
        "arena_buddy.web.app",
        "arena_buddy.web.routes",
        "arena_buddy.web.server",
        "arena_buddy.web.websocket",
        "arena_buddy.core",
        "arena_buddy.core.game_state",
        "arena_buddy.core.match_capture",
        "arena_buddy.core.match_capture_service",
        "arena_buddy.core.orchestrator",
        "arena_buddy.core.league_detector",
        "arena_buddy.core.riot_api",
        "arena_buddy.assets",
        "arena_buddy.assets.icons",
        "arena_buddy.scraper",
        "arena_buddy.scraper.lolalytics",
        "arena_buddy.scraper.browser_scraper",
        "arena_buddy.scraper.name_matcher",
        "arena_buddy.scraper.qwik_scraper",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "email",
        "http",
        "xmlrpc",
        "pydoc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# ---------------------------------------------------------------------------
# Additional data from package metadata
# ---------------------------------------------------------------------------

# Collect data files from installed packages
for pkg in ["fastapi"]:
    try:
        datas = collect_data_files(pkg)
        if datas:
            a.datas += datas
    except Exception:
        pass

# ---------------------------------------------------------------------------
# PYZ (compiled .pyz archive)
# ---------------------------------------------------------------------------

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# ---------------------------------------------------------------------------
# EXE
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ArenaBuddy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window — GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="src/arena_buddy/web/static/icon.ico" if False else None,  # TODO: add icon
)
