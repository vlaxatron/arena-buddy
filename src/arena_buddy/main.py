"""Main entry point for Arena Buddy.

Starts the FastAPI server and opens the UI in a desktop window
(Windows: pywebview with WebView2) or browser (Linux: fallback).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# PyInstaller with console=False nulls out stdout/stderr, which crashes
# uvicorn's logging.  Redirect them to a log file so errors are always
# visible even without a console.
# ---------------------------------------------------------------------------
_LOG_PATH: Path | None = None


def _init_logging() -> Path:
    """Set up file-based logging.  Called before any imports that might fail."""
    from arena_buddy.config import get_app_dir

    log_dir = get_app_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "arena_buddy.log"
    global _LOG_PATH
    _LOG_PATH = log_path

    # Open log file for appending
    log_fh = open(log_path, "a", encoding="utf-8")
    log_fh.write(f"\n--- Arena Buddy started at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_fh.flush()

    if sys.stderr is None:
        sys.stderr = log_fh
    if sys.stdout is None:
        sys.stdout = log_fh
    return log_path


def _log_error(msg: str) -> None:
    """Write an error message to the log file."""
    try:
        if _LOG_PATH:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"ERROR: {msg}\n")
                f.flush()
    except Exception:
        pass


# Init logging early
try:
    _init_logging()
except Exception:
    pass

import uvicorn

from arena_buddy.config import get_db_path
from arena_buddy.db.connection import init_database
from arena_buddy.web.app import create_app
from arena_buddy.web.server import get_host, get_port


def _server_runner(server: uvicorn.Server) -> None:
    """Run the uvicorn server and log any unhandled exceptions."""
    try:
        server.run()
    except Exception:
        _log_error(traceback.format_exc())
        raise


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    """Poll the health endpoint until the server responds or timeout."""
    import urllib.request
    import urllib.error

    health_url = f"{url}/api/health"
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(health_url, timeout=2)
            if resp.status == 200:
                return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.3)
    return False


def _open_window(url: str) -> None:
    """Open the Arena Buddy UI (pywebview on Windows, browser fallback)."""
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
            pass
        except Exception as exc:
            _log_error(f"pywebview: {exc}")

    # Fallback: open in default browser
    webbrowser.open(url)


def main() -> None:
    """Run Arena Buddy — start server and open UI window."""
    try:
        db_path = get_db_path()
        init_database(db_path)
    except Exception:
        _log_error(f"DB init failed:\n{traceback.format_exc()}")
        _show_error("Database initialization failed.")
        sys.exit(1)

    host = get_host()
    port = get_port()
    url = f"http://{host}:{port}"

    # Build the app and server
    try:
        app = create_app(db_path=db_path)
    except Exception:
        _log_error(f"App creation failed:\n{traceback.format_exc()}")
        _show_error("Failed to create application.")
        sys.exit(1)

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(
        target=_server_runner, args=(server,), daemon=True
    )
    server_thread.start()

    # Wait for the server to be ready
    if not _wait_for_server(url, timeout=20):
        _show_error("Server did not start in time.")
        sys.exit(1)

    # Open the window
    _open_window(url)

    # Keep alive
    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass


def _show_error(message: str) -> None:
    """Show an error to the user (message box on Windows, print otherwise)."""
    log_path_str = str(_LOG_PATH) if _LOG_PATH else "arena_buddy.log"
    full_msg = f"{message}\n\nCheck the log file for details:\n{log_path_str}"

    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0, full_msg, "Arena Buddy - Error", 0x10,
            )
        except Exception:
            print(full_msg, file=sys.stderr)
    else:
        print(full_msg, file=sys.stderr)


if __name__ == "__main__":
    main()
