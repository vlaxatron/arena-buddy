"""Icon downloader — caches champion / item / augment icons from CDN sources.

Downloads from Data Dragon and CommunityDragon, stores results under the
configured cache directory, and supports batched downloads with progress
callbacks and graceful error handling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import httpx

from arena_buddy.config import get_cache_dir

# ---------------------------------------------------------------------------
# CDN base URLs
# ---------------------------------------------------------------------------

_DDRAGON_BASE = "https://ddragon.leagueoflegends.com/cdn/16.11.1"
_CDRAGON_AUGMENT_BASE = (
    "https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons"
)

# ---------------------------------------------------------------------------
# In-memory download tracker (session-scoped; resets on module reload)
# ---------------------------------------------------------------------------

_downloaded: set[Path] = set()


def _get_client() -> httpx.Client:
    """Return an :class:`httpx.Client` with retry transport configured."""
    transport = httpx.HTTPTransport(retries=3)
    return httpx.Client(transport=transport)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _download_and_cache(url: str, local_path: Path) -> Path:
    """Download *url* to *local_path*, skipping if already cached.

    Returns *local_path* on success.  Raises :class:`httpx.HTTPStatusError`
    or :class:`httpx.RequestError` on failure.
    """
    if local_path in _downloaded or local_path.exists():
        return local_path

    with _get_client() as client:
        response = client.get(url)
        response.raise_for_status()

    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(response.content)
    _downloaded.add(local_path)
    return local_path


# ---------------------------------------------------------------------------
# Single-icon public API
# ---------------------------------------------------------------------------

def download_champion_icon(champion_key: str, icon_filename: str) -> Path:
    """Download a champion icon from Data Dragon and cache it.

    Args:
        champion_key: Internal champion key (e.g. ``"Lucian"``).
        icon_filename: Icon filename from Data Dragon (e.g. ``"Lucian.png"``).

    Returns:
        Path to the cached file on disk.
    """
    url = f"{_DDRAGON_BASE}/img/champion/{icon_filename}"
    local_path = get_cache_dir() / "champions" / icon_filename
    return _download_and_cache(url, local_path)


def download_item_icon(item_id: int) -> Path:
    """Download an item icon from Data Dragon and cache it.

    Args:
        item_id: Numeric item identifier (e.g. ``1001``).

    Returns:
        Path to the cached file on disk.
    """
    url = f"{_DDRAGON_BASE}/img/item/{item_id}.png"
    local_path = get_cache_dir() / "items" / f"{item_id}.png"
    return _download_and_cache(url, local_path)


def download_augment_icon(api_name: str) -> Path:
    """Download an augment icon from CommunityDragon and cache it.

    Args:
        api_name: CommunityDragon *apiName* (e.g. ``"WarmupRoutine"``).

    Returns:
        Path to the cached file on disk.
    """
    # CommunityDragon stores icons with lowercase filenames
    url = f"{_CDRAGON_AUGMENT_BASE}/{api_name.lower()}_large.png"
    local_path = get_cache_dir() / "augments" / f"{api_name}.png"
    return _download_and_cache(url, local_path)


# ---------------------------------------------------------------------------
# Batch (bulk) download helpers
# ---------------------------------------------------------------------------

def _batch_download(
    items: list,
    download_fn: Callable,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> list[Path]:
    """Download a list of items using *download_fn*, collecting successes.

    Each item is passed to ``download_fn(item)``.  Errors (HTTP or network)
    are caught silently so one failure never aborts the batch.

    Args:
        items: Iterable of arguments to pass to *download_fn*.
        download_fn: Single-icon download function (champion / item / augment).
        on_progress: Optional ``(current, total)`` callback after each attempt.

    Returns:
        List of :class:`Path` objects for successfully downloaded icons.
    """
    results: list[Path] = []
    total = len(items)

    for idx, item in enumerate(items, start=1):
        try:
            path = download_fn(item)
            results.append(path)
        except (httpx.HTTPStatusError, httpx.RequestError):
            # Logged / reported at a higher layer if needed; silently skip here.
            pass
        if on_progress is not None:
            on_progress(idx, total)

    return results


def download_all_champion_icons(
    champions: list[tuple[str, str]],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> list[Path]:
    """Bulk-download champion icons.

    Args:
        champions: List of ``(champion_key, icon_filename)`` tuples.
        on_progress: Optional ``(current, total)`` callback.

    Returns:
        Paths of successfully downloaded champion icons.
    """
    def _dl(champ_tuple: tuple[str, str]) -> Path:
        key, filename = champ_tuple
        return download_champion_icon(key, filename)

    return _batch_download(champions, _dl, on_progress=on_progress)


def download_all_item_icons(
    items: list[int],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> list[Path]:
    """Bulk-download item icons.

    Args:
        items: List of numeric item IDs.
        on_progress: Optional ``(current, total)`` callback.

    Returns:
        Paths of successfully downloaded item icons.
    """
    return _batch_download(items, download_item_icon, on_progress=on_progress)


def download_all_augment_icons(
    augments: list[str],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> list[Path]:
    """Bulk-download augment icons.

    Args:
        augments: List of CommunityDragon *apiName* strings.
        on_progress: Optional ``(current, total)`` callback.

    Returns:
        Paths of successfully downloaded augment icons.
    """
    return _batch_download(augments, download_augment_icon, on_progress=on_progress)


# ---------------------------------------------------------------------------
# Lazy icon ensure — call when champion data is loaded
# ---------------------------------------------------------------------------

def ensure_icons_for_champion(
    champion_key: str,
    champion_icon: str,
    item_ids: list[int],
    augment_api_names: list[str],
) -> dict[str, int]:
    """Ensure all icons for a champion are cached locally.

    Downloads any missing champion, item, and augment icons from their
    respective CDN sources.  Skips files that already exist on disk
    (each ``download_*`` function checks for existence first).

    Args:
        champion_key: Internal champion key (e.g. ``"Lucian"``).
        champion_icon: Champion icon filename (e.g. ``"Lucian.png"``).
        item_ids: List of numeric item IDs to download icons for.
        augment_api_names: List of augment *apiName* strings.

    Returns:
        A dict with counts::
            {"champion": N, "item": N, "augment": N, "skipped": N}
    """
    result: dict[str, int] = {"champion": 0, "item": 0, "augment": 0, "skipped": 0}

    try:
        download_champion_icon(champion_key, champion_icon)
        result["champion"] = 1
    except (httpx.HTTPStatusError, httpx.RequestError):
        result["skipped"] += 1

    for item_id in item_ids:
        try:
            download_item_icon(item_id)
            result["item"] += 1
        except (httpx.HTTPStatusError, httpx.RequestError):
            result["skipped"] += 1

    for api_name in augment_api_names:
        try:
            download_augment_icon(api_name)
            result["augment"] += 1
        except (httpx.HTTPStatusError, httpx.RequestError):
            result["skipped"] += 1

    return result
