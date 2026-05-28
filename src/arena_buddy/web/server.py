"""Uvicorn server launcher for Arena Buddy."""

from __future__ import annotations

import os


def get_port() -> int:
    """Return the port to listen on, respecting ARENA_BUDDY_PORT env var.

    Default: 8765 (avoids common dev ports).
    """
    return int(os.environ.get("ARENA_BUDDY_PORT", "8765"))


def get_host() -> str:
    """Return the host to bind to.

    Default: 127.0.0.1 (local only — no network exposure).
    """
    return os.environ.get("ARENA_BUDDY_HOST", "127.0.0.1")
