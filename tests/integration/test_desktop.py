"""Integration tests for main entry point and server launcher."""

import pytest


class TestServerLauncher:
    """Tests for the uvicorn server launcher."""

    def test_get_port_returns_integer(self):
        """Default port is an integer."""
        from arena_buddy.web.server import get_port
        port = get_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_get_port_respects_env(self, monkeypatch):
        """Port can be overridden via ARENA_BUDDY_PORT env var."""
        monkeypatch.setenv("ARENA_BUDDY_PORT", "9999")

        from arena_buddy.web.server import get_port
        port = get_port()
        assert port == 9999

    def test_get_host_default(self):
        """Default host is 127.0.0.1."""
        from arena_buddy.web.server import get_host
        host = get_host()
        assert host == "127.0.0.1"


class TestMainFlow:
    """Smoke tests for main entry point."""

    def test_main_importable(self):
        """The main module can be imported."""
        from arena_buddy import main
        assert hasattr(main, "main")

    def test_main_callable(self):
        """main() is callable."""
        from arena_buddy.main import main
        assert callable(main)
