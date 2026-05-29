"""Main entry point for Arena Buddy.

Starts the FastAPI server and opens the UI in a desktop window
(Windows: pywebview with WebView2) or browser (Linux: fallback).
"""

from __future__ import annotations

import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from arena_buddy.config import get_db_path
from arena_buddy.db.connection import init_database
from arena_buddy.web.app import create_app
from arena_buddy.web.server import get_host, get_port


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """Poll the health endpoint until the server responds or timeout.

    Returns True if the server came up, False otherwise.
    """
    import urllib.request
    import urllib.error

    health_url = f"{url}/api/health"
    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(health_url, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
            last_error = exc
        time.sleep(0.3)

    if last_error:
        print(f"Server failed to start: {last_error}", file=sys.stderr)
    return False


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
        except Exception as exc:
            print(f"pywebview failed: {exc}", file=sys.stderr)
            # Fall back to browser

    # Fallback: open in default browser
    print(f"Arena Buddy running at {url}")
    webbrowser.open(url)


def main() -> None:
    """Run Arena Buddy — start server and open UI window."""
    db_path = get_db_path()
    init_database(db_path)

    host = get_host()
    port = get_port()
    url = f"http://{host}:{port}"

    # Start uvicorn in a background daemon thread
    app = create_app(db_path=db_path)
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for the server to actually be ready (health check loop)
    print(f"Starting Arena Buddy on {url} ...")
    if not _wait_for_server(url):
        print("ERROR: Server did not start. Check logs above.", file=sys.stderr)
        if sys.platform == "win32":
            # On Windows with no console, try to show a message
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(
                    0,
                    "Arena Buddy could not start the server.\n\n"
                    "Try running from a command prompt to see error details:\n"
                    "  arena-buddy",
                    "Arena Buddy - Startup Error",
                    0x10,  # MB_ICONERROR
                )
            except Exception:
                pass
        sys.exit(1)

    # Open the window
    _open_window(url)

    # Keep the main thread alive while the server runs
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\nArena Buddy shutting down.")


if __name__ == "__main__":
    main()
