"""Tests for arena_buddy.config — cross-platform path resolution."""

import os
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# We'll test the module after importing it
# Tests written first — these WILL fail until config.py exists


class TestGetAppDir:
    """Tests for get_app_dir() — platform-appropriate app data directory."""

    def test_linux_uses_xdg_data_home(self, monkeypatch, tmp_path):
        """On Linux, use XDG_DATA_HOME if set."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        from arena_buddy.config import get_app_dir

        result = get_app_dir()
        assert result == tmp_path / "arena-buddy"

    def test_linux_falls_back_to_dot_local_share(self, monkeypatch):
        """On Linux, fall back to ~/.local/share/arena-buddy if no XDG_DATA_HOME."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setenv("HOME", "/home/testuser")

        from arena_buddy.config import get_app_dir

        result = get_app_dir()
        assert result == Path("/home/testuser/.local/share/arena-buddy")

    def test_windows_uses_appdata(self, monkeypatch):
        """On Windows, use %APPDATA%/ArenaBuddy."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")

        from arena_buddy.config import get_app_dir

        result = get_app_dir()
        assert result == Path("C:/Users/test/AppData/Roaming/ArenaBuddy")


class TestGetDbPath:
    """Tests for get_db_path()."""

    def test_returns_path_in_app_dir(self, monkeypatch, tmp_path):
        """get_db_path returns {app_dir}/arena_buddy.db."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        from arena_buddy.config import get_db_path

        result = get_db_path()
        expected = tmp_path / "arena-buddy" / "arena_buddy.db"
        assert result == expected
        # Parent dir should exist after call
        assert expected.parent.exists()

    def test_app_dir_created_if_missing(self, monkeypatch, tmp_path):
        """Ensure parent directories are created."""
        app_dir = tmp_path / "arena-buddy"
        assert not app_dir.exists()

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        from arena_buddy.config import get_db_path

        get_db_path()
        assert app_dir.exists()


class TestGetCacheDir:
    """Tests for get_cache_dir()."""

    def test_linux_cache_in_xdg_cache_home(self, monkeypatch, tmp_path):
        """On Linux, cache goes to XDG_CACHE_HOME/arena-buddy."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        from arena_buddy.config import get_cache_dir

        result = get_cache_dir()
        assert result == tmp_path / "arena-buddy"

    def test_windows_cache_in_appdata(self, monkeypatch):
        """On Windows, cache goes to %APPDATA%/ArenaBuddy/cache."""
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")

        from arena_buddy.config import get_cache_dir

        result = get_cache_dir()
        assert result == Path("C:/Users/test/AppData/Roaming/ArenaBuddy/cache")


class TestGetConfigPath:
    """Tests for get_config_path()."""

    def test_linux_config_in_xdg_config_home(self, monkeypatch, tmp_path):
        """On Linux, config goes to XDG_CONFIG_HOME/arena-buddy/settings.json."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from arena_buddy.config import get_config_path

        result = get_config_path()
        assert result == tmp_path / "arena-buddy" / "settings.json"


class TestLoadSaveSettings:
    """Tests for load_settings() and save_settings()."""

    def test_load_returns_defaults_when_no_file(self, monkeypatch, tmp_path):
        """When no settings file exists, return sensible defaults."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from arena_buddy.config import load_settings

        settings = load_settings()
        assert isinstance(settings, dict)
        assert "window" in settings
        assert settings["window"]["width"] > 0
        assert settings["window"]["height"] > 0

    def test_save_and_load_roundtrip(self, monkeypatch, tmp_path):
        """Save settings, then load them back (merge with defaults)."""
        config_dir = tmp_path / "arena-buddy"
        config_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from arena_buddy.config import load_settings, save_settings

        test_settings = {
            "window": {"x": 100, "y": 200, "width": 800, "height": 600},
            "always_on_top": False,
        }
        save_settings(test_settings)

        loaded = load_settings()
        # User-provided values should be preserved
        assert loaded["window"] == test_settings["window"]
        assert loaded["always_on_top"] == test_settings["always_on_top"]
        # Default keys not in test_settings should still be present
        assert "last_champion_key" in loaded

    def test_save_creates_parent_dirs(self, monkeypatch, tmp_path):
        """save_settings creates parent directories if missing."""
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from arena_buddy.config import save_settings

        save_settings({"test": True})

        config_dir = tmp_path / "arena-buddy"
        assert config_dir.exists()
        assert (config_dir / "settings.json").exists()
