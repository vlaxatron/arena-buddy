"""Tests for arena_buddy.core.league_detector — cross-platform League install detection.

Tests written FIRST (RED phase) — these WILL fail until league_detector.py exists.
"""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_league_install(base: Path, with_lockfile: bool = False) -> Path:
    """Create a minimal fake League install directory for testing.

    Creates ``base/LeagueClient.exe`` and optionally a lockfile.
    """
    league_dir = base
    league_dir.mkdir(parents=True, exist_ok=True)
    (league_dir / "LeagueClient.exe").write_text("fake")
    if with_lockfile:
        (league_dir / "lockfile").write_text(
            "LeagueClient:12345:56789:password123:https"
        )
    return league_dir


# ---------------------------------------------------------------------------
# find_league_install
# ---------------------------------------------------------------------------

class TestFindLeagueInstallWindows:
    """League detection on Windows."""

    def test_finds_in_default_riot_games_c_drive(self, monkeypatch, tmp_path):
        """Should find League via known Windows paths."""
        monkeypatch.setattr(sys, "platform", "win32")
        install = _make_fake_league_install(tmp_path / "Riot Games" / "League of Legends")

        # Override search roots for testing
        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.find_league_install()
        assert result is not None
        assert (result / "LeagueClient.exe").exists()

    def test_returns_none_when_not_found_windows(self, monkeypatch, tmp_path):
        """Should return None when no League install on Windows."""
        monkeypatch.setattr(sys, "platform", "win32")

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.find_league_install()
        assert result is None


class TestFindLeagueInstallLinux:
    """League detection on Linux (Wine/Lutris prefixes)."""

    def test_finds_in_wine_prefix(self, monkeypatch, tmp_path):
        """Should find League in ~/.wine/drive_c/Riot Games/League of Legends."""
        monkeypatch.setattr(sys, "platform", "linux")
        wine_dir = tmp_path / ".wine" / "drive_c"
        _make_fake_league_install(wine_dir / "Riot Games" / "League of Legends")
        monkeypatch.setenv("HOME", str(tmp_path))

        from arena_buddy.core import league_detector

        result = league_detector.find_league_install()
        assert result is not None
        assert (result / "LeagueClient.exe").exists()

    def test_finds_in_lutris_default(self, monkeypatch, tmp_path):
        """Should find League in ~/Games/league-of-legends (Lutris default)."""
        monkeypatch.setattr(sys, "platform", "linux")
        lutris_dir = tmp_path / "Games" / "league-of-legends" / "drive_c"
        _make_fake_league_install(lutris_dir / "Riot Games" / "League of Legends")
        monkeypatch.setenv("HOME", str(tmp_path))

        from arena_buddy.core import league_detector

        result = league_detector.find_league_install()
        assert result is not None

    def test_returns_none_when_not_found(self, monkeypatch, tmp_path):
        """Should return None when no League install found."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("HOME", str(tmp_path))

        from arena_buddy.core import league_detector

        result = league_detector.find_league_install()
        assert result is None


class TestFindLeagueInstallMacOS:
    """League detection on macOS."""

    def test_finds_in_applications(self, monkeypatch, tmp_path):
        """Should find League in /Applications/League of Legends.app."""
        monkeypatch.setattr(sys, "platform", "darwin")
        # Create fake .app structure
        league_dir = tmp_path / "League of Legends.app" / "Contents" / "LoL"
        league_dir.mkdir(parents=True)
        (league_dir / "LeagueClient").write_text("fake")

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_MACOS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.find_league_install()
        assert result is not None


# ---------------------------------------------------------------------------
# get_league_lockfile_path
# ---------------------------------------------------------------------------

class TestGetLeagueLockfilePath:
    """Lockfile path detection."""

    def test_lockfile_detected_when_exists(self, monkeypatch, tmp_path):
        """Finds lockfile in the League install directory."""
        monkeypatch.setattr(sys, "platform", "win32")
        install = _make_fake_league_install(
            tmp_path / "Riot Games" / "League of Legends",
            with_lockfile=True,
        )

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.get_league_lockfile_path()
        assert result is not None
        assert result.name == "lockfile"

    def test_returns_none_when_no_lockfile(self, monkeypatch, tmp_path):
        """Returns None when League is not running (no lockfile)."""
        monkeypatch.setattr(sys, "platform", "win32")
        _make_fake_league_install(
            tmp_path / "Riot Games" / "League of Legends",
            with_lockfile=False,
        )

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.get_league_lockfile_path()
        assert result is None


# ---------------------------------------------------------------------------
# get_league_game_path
# ---------------------------------------------------------------------------

class TestGetLeagueGamePath:
    """Game directory detection (contains League of Legends.exe)."""

    def test_game_path_is_game_subdir(self, monkeypatch, tmp_path):
        """The game executable is in <install>/Game/League of Legends.exe."""
        monkeypatch.setattr(sys, "platform", "win32")
        install_dir = tmp_path / "Riot Games" / "League of Legends"
        game_dir = install_dir / "Game"
        game_dir.mkdir(parents=True)
        (install_dir / "LeagueClient.exe").write_text("fake")
        (game_dir / "League of Legends.exe").write_text("fake")

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.get_league_game_path()
        assert result is not None
        assert result.name == "Game"

    def test_returns_none_when_not_found(self, monkeypatch, tmp_path):
        """Returns None when no install found."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("HOME", str(tmp_path))

        from arena_buddy.core import league_detector

        result = league_detector.get_league_game_path()
        assert result is None


# ---------------------------------------------------------------------------
# is_league_running
# ---------------------------------------------------------------------------

class TestIsLeagueRunning:
    """Check whether LCU is running (lockfile exists and is fresh)."""

    def test_returns_true_when_lockfile_exists(self, monkeypatch, tmp_path):
        """True when lockfile is present."""
        monkeypatch.setattr(sys, "platform", "win32")
        _make_fake_league_install(
            tmp_path / "Riot Games" / "League of Legends",
            with_lockfile=True,
        )

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.is_league_running()
        assert result is True

    def test_returns_false_when_no_lockfile(self, monkeypatch, tmp_path):
        """False when no lockfile present."""
        monkeypatch.setattr(sys, "platform", "win32")

        from arena_buddy.core import league_detector

        monkeypatch.setattr(
            league_detector,
            "_WINDOWS_SEARCH_ROOTS",
            [str(tmp_path)],
        )

        result = league_detector.is_league_running()
        assert result is False
