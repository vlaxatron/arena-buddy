"""Cross-platform League of Legends installation detection.

Finds the League of Legends install directory, lockfile, and game
executable across Windows, Linux (Wine/Lutris), and macOS.
"""

from __future__ import annotations

import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Platform-specific search roots
# ---------------------------------------------------------------------------

_WINDOWS_SEARCH_ROOTS: list[str] = [
    "C:/Riot Games",
    "D:/Riot Games",
    "E:/Riot Games",
    "C:/Program Files/Riot Games",
    "C:/Program Files (x86)/Riot Games",
]

_LINUX_SEARCH_ROOTS: list[str] = [
    "{home}/.wine/drive_c",
    "{home}/Games/league-of-legends/drive_c",
    "{home}/.local/share/lutris/games/league-of-legends/drive_c",
    "/mnt",  # Scan mounted drives for dual-boot
]

# Lutris prefixes may also nest under Games/ with different game names
_LINUX_LEAGUE_DIRS: list[str] = [
    "Riot Games/League of Legends",
]

_MACOS_SEARCH_ROOTS: list[str] = [
    "/Applications",
]


def _expand_home(path: str, home: str) -> str:
    """Replace ``{home}`` placeholder with the actual home directory."""
    return path.replace("{home}", home)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_league_install() -> Path | None:
    """Find the League of Legends install directory.

    Searches platform-specific known locations for ``LeagueClient.exe``
    (Windows/Linux via Wine) or ``LeagueClient`` (macOS).

    Returns:
        Absolute path to the install directory, or ``None`` if not found.
    """
    if sys.platform == "win32":
        search_roots = _WINDOWS_SEARCH_ROOTS
        client_exe = "LeagueClient.exe"
    elif sys.platform == "darwin":
        search_roots = _MACOS_SEARCH_ROOTS
        client_exe = "LeagueClient"
    else:
        # Linux
        import os as _os
        home = _os.environ.get("HOME", str(Path.home()))
        search_roots = [
            _expand_home(r, home)
            for r in _LINUX_SEARCH_ROOTS
        ]
        client_exe = "LeagueClient.exe"

    candidate_dirs = _candidate_install_dirs(search_roots, client_exe, sys.platform)
    return candidate_dirs


def _candidate_install_dirs(
    roots: list[str], client_exe: str, platform: str
) -> Path | None:
    """Walk search roots to find League install dir."""
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue

        # For /mnt, scan subdirectories (mounted drives)
        if platform not in ("win32", "darwin") and root_path.name == "mnt":
            for drive in root_path.iterdir():
                if not drive.is_dir():
                    continue
                for league_dir in _LINUX_LEAGUE_DIRS:
                    candidate = drive / league_dir
                    if (candidate / client_exe).exists():
                        return candidate
        else:
            # Windows/macOS: direct path or nested
            for league_dir in _LINUX_LEAGUE_DIRS:
                candidate = root_path / league_dir
                if (candidate / client_exe).exists():
                    return candidate

            # macOS: scan for League of Legends.app
            if platform == "darwin":
                for item in root_path.iterdir():
                    if not item.is_dir():
                        continue
                    # Look for .app bundle
                    candidate = item / "Contents" / "LoL"
                    if client_exe == "LeagueClient":
                        # macOS uses plain "LeagueClient" binary
                        if (candidate / "LeagueClient").exists():
                            return candidate
                    # Also check for Unix-style path inside .app
                    lol_dir = item / "Contents" / "LoL"
                    if (lol_dir / client_exe).exists():
                        return lol_dir

    return None


def get_league_lockfile_path() -> Path | None:
    """Return the path to the LCU lockfile, or ``None`` if not running.

    The lockfile is created by the League Client when it's running and
    contains the port and password for the LCU API.
    """
    install = find_league_install()
    if install is None:
        return None

    lockfile = install / "lockfile"
    if lockfile.exists():
        return lockfile
    return None


def get_league_game_path() -> Path | None:
    """Return the path to the League game directory (Game/ subfolder).

    This is where ``League of Legends.exe`` lives — needed for launching
    the actual game client (not the lobby).
    """
    install = find_league_install()
    if install is None:
        return None

    game_dir = install / "Game"
    if game_dir.exists():
        return game_dir
    return None


def is_league_running() -> bool:
    """Check whether the League Client (LCU) is currently running.

    Returns:
        ``True`` if the lockfile exists (LCU is running), ``False`` otherwise.
    """
    return get_league_lockfile_path() is not None
