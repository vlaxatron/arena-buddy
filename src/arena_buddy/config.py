"""Cross-platform configuration and path resolution for Arena Buddy.

Handles app data directories, database path, cache directory, and
settings persistence across Linux (XDG) and Windows (%APPDATA%).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    """Return True when running on Windows (lazily evaluated for testability)."""
    return sys.platform == "win32"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_app_dir() -> Path:
    """Return the platform-appropriate application data directory.

    Linux:   ``$XDG_DATA_HOME/arena-buddy`` or ``~/.local/share/arena-buddy``
    Windows: ``%APPDATA%\\ArenaBuddy``
    """
    if _is_windows():
        raw = os.environ.get("APPDATA", "")
        if raw:
            raw = raw.replace("\\", "/")
        else:
            raw = str(Path.home() / "AppData" / "Roaming")
        return Path(raw) / "ArenaBuddy"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        if base:
            return Path(base) / "arena-buddy"
        home = Path(os.environ.get("HOME", Path.home()))
        return home / ".local" / "share" / "arena-buddy"


def get_db_path() -> Path:
    """Return the full path to the SQLite database file.

    Creates the parent directory if it does not exist.
    """
    app_dir = get_app_dir()
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir / "arena_buddy.db"


def get_cache_dir() -> Path:
    """Return the icon / static asset cache directory.

    Linux:   ``$XDG_CACHE_HOME/arena-buddy`` or ``~/.cache/arena-buddy``
    Windows: ``%APPDATA%\\ArenaBuddy\\cache``
    """
    if _is_windows():
        return get_app_dir() / "cache"
    else:
        base = os.environ.get("XDG_CACHE_HOME")
        if base:
            return Path(base) / "arena-buddy"
        home = Path(os.environ.get("HOME", Path.home()))
        return home / ".cache" / "arena-buddy"


def get_config_path() -> Path:
    """Return the path to the settings JSON file.

    Linux:   ``$XDG_CONFIG_HOME/arena-buddy/settings.json``
    Windows: ``%APPDATA%\\\\ArenaBuddy\\\\config\\\\settings.json``
    """
    if _is_windows():
        return get_app_dir() / "config" / "settings.json"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        if base:
            return Path(base) / "arena-buddy" / "settings.json"
        home = Path(os.environ.get("HOME", Path.home()))
        return home / ".config" / "arena-buddy" / "settings.json"


def get_ddragon_version() -> str:
    """Return the cached Data Dragon version, falling back to the last known good.

    The version file is written by :func:`arena_buddy.db.seed._download_data_files`
    during the first-run auto-download.  If the cache hasn't been populated
    yet (or the file is corrupt), returns a sensible default so icon URLs
    don't 404.

    Returns:
        A full patch version string like ``"16.11.1"``.
    """
    version_path = get_cache_dir() / "data" / "ddragon_version.txt"
    try:
        cached = version_path.read_text().strip()
        if cached:
            return cached
    except (OSError, UnicodeDecodeError):
        pass
    # Fallback: last known good version at time of release.
    # When the auto-download runs, this will be overwritten with the actual
    # latest version, so this fallback only matters on the very first launch
    # before the download completes.
    return "16.11.1"


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "window": {"width": 1024, "height": 768, "x": None, "y": None},
    "always_on_top": False,
    "last_champion_key": None,
}


def load_settings() -> dict:
    """Load settings from disk, merging with defaults.

    Returns:
        A dict with all default keys populated.  Missing keys in the
        on-disk JSON are filled from ``_DEFAULTS``.
    """
    path = get_config_path()
    if not path.exists():
        return _DEFAULTS.copy()

    try:
        with open(path, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return _DEFAULTS.copy()

    # Shallow-merge: stored keys override defaults
    merged = _DEFAULTS.copy()
    merged.update(stored)
    return merged


def save_settings(settings: dict) -> None:
    """Persist settings to disk as JSON.

    Creates parent directories if they do not exist.
    """
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Merge with defaults so we always save a complete config
    data = _DEFAULTS.copy()
    data.update(settings)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
