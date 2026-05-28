"""Main entry point for Arena Buddy.

Starts the FastAPI server and opens the UI in a desktop window
(Windows: pywebview with WebView2) or browser (Linux: fallback).
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from arena_buddy.config import get_db_path
from arena_buddy.db.connection import init_database
from arena_buddy.db.seed import seed_all
from arena_buddy.web.app import create_app
from arena_buddy.web.server import get_host, get_port


def _open_window(url: str) -> None:
    """Open the Arena Buddy UI.

    On Windows, attempts to use pywebview for a native window.
    Falls back to opening the default browser on all platforms.
    """
    if sys.platform == "win32":
        try:
            import webview  # type: ignore[import-untyped]
            webview.create_window(
                title="Arena Buddy",
                url=url,
                width=1024,
                height=768,
                resizable=True,
            )
            webview.start()
            return
        except ImportError:
            pass  # Fall back to browser
        except Exception:
            pass  # Fall back to browser

    # Fallback: open in default browser
    print(f"Arena Buddy running at {url}")
    webbrowser.open(url)


def main() -> None:
    """Run Arena Buddy — start server and open UI window."""
    db_path = get_db_path()

    # Ensure database is initialized and seeded
    init_database(db_path)

    host = get_host()
    port = get_port()
    url = f"http://{host}:{port}"

    # Start uvicorn in a background thread so the window can open immediately
    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": "arena_buddy.web.app:create_app",
            "host": host,
            "port": port,
            "log_level": "info",
        },
        daemon=True,
    )
    server_thread.start()

    # Give the server a moment to start
    import time
    time.sleep(0.5)

    # Open the window
    _open_window(url)

    # Keep the main thread alive while the server runs
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\nArena Buddy shutting down.")


if __name__ == "__main__":
    main()
