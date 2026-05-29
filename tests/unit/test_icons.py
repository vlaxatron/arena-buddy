"""Tests for arena_buddy.assets.icons — icon downloader module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # minimal valid PNG header


def _fake_response(status_code=200, content=FAKE_PNG, url=""):
    """Build a fake httpx.Response for a successful image download."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    resp.url = url
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        error = httpx.HTTPStatusError(
            f"{status_code} error", request=MagicMock(), response=resp
        )
        resp.raise_for_status.side_effect = error
    return resp


def _make_mock_client(response_map=None, default_status=200, default_content=FAKE_PNG):
    """Create a MagicMock httpx.Client whose .get(url) returns a fake response.

    *response_map*: dict[str, httpx.Response] — exact URL → response.
    *default_status/content*: used for URLs not in the map.
    """
    client = MagicMock()

    def _get(url, **kwargs):
        if response_map and url in response_map:
            return response_map[url]
        return _fake_response(status_code=default_status, content=default_content, url=url)

    client.get.side_effect = _get
    client.__enter__.return_value = client
    client.__exit__.return_value = False
    return client


# ---------------------------------------------------------------------------
# Test single-icon downloads
# ---------------------------------------------------------------------------

class TestDownloadChampionIcon:
    """Unit tests for download_champion_icon()."""

    def test_downloads_and_returns_path(self, monkeypatch, temp_cache_dir):
        """A successful download returns the local cache path."""
        from arena_buddy.assets.icons import download_champion_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        path = download_champion_icon("Lucian", "Lucian.png")
        assert path.exists()
        assert path.suffix == ".png"
        assert path.parent == temp_cache_dir / "champions"

    def test_skips_re_download_when_file_exists(self, monkeypatch, temp_cache_dir):
        """If the file already exists on disk, no HTTP request is made."""
        from arena_buddy.assets.icons import download_champion_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        # Pre-create the cached file
        cache_file = temp_cache_dir / "champions" / "Lucian.png"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(FAKE_PNG)

        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        path = download_champion_icon("Lucian", "Lucian.png")
        assert path == cache_file
        # Client.get should NOT have been called
        mock_client.get.assert_not_called()

    def test_handles_404_gracefully(self, monkeypatch, temp_cache_dir):
        """A 404 response raises an exception (caller can catch)."""
        from arena_buddy.assets.icons import download_champion_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(default_status=404),
        )

        with pytest.raises(httpx.HTTPStatusError):
            download_champion_icon("Missing", "Missing.png")


class TestDownloadItemIcon:
    """Unit tests for download_item_icon()."""

    def test_downloads_item_icon(self, monkeypatch, temp_cache_dir):
        """Downloads an item icon to cache/items/<id>.png."""
        from arena_buddy.assets.icons import download_item_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        path = download_item_icon(1001)
        assert path.exists()
        assert path.name == "1001.png"
        assert path.parent == temp_cache_dir / "items"

    def test_skips_existing_item(self, monkeypatch, temp_cache_dir):
        """Already-cached item icons are not re-downloaded."""
        from arena_buddy.assets.icons import download_item_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        cache_file = temp_cache_dir / "items" / "1001.png"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(FAKE_PNG)

        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        path = download_item_icon(1001)
        assert path == cache_file
        mock_client.get.assert_not_called()


class TestDownloadAugmentIcon:
    """Unit tests for download_augment_icon()."""

    def test_downloads_augment_icon(self, monkeypatch, temp_cache_dir):
        """Downloads an augment icon from CommunityDragon."""
        from arena_buddy.assets.icons import download_augment_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        path = download_augment_icon("WarmupRoutine")
        assert path.exists()
        assert path.name == "WarmupRoutine.png"
        assert path.parent == temp_cache_dir / "augments"

    def test_skips_existing_augment(self, monkeypatch, temp_cache_dir):
        """Already-cached augment icons are not re-downloaded."""
        from arena_buddy.assets.icons import download_augment_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        cache_file = temp_cache_dir / "augments" / "WarmupRoutine.png"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(FAKE_PNG)

        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        path = download_augment_icon("WarmupRoutine")
        assert path == cache_file
        mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# Test batch downloads
# ---------------------------------------------------------------------------

class TestDownloadAllChampionIcons:
    """Tests for download_all_champion_icons()."""

    def test_downloads_multiple_champions(self, monkeypatch, temp_cache_dir):
        """Downloads icons for a list of champions and returns paths."""
        from arena_buddy.assets.icons import download_all_champion_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        champions = [
            ("Lucian", "Lucian.png"),
            ("Jinx", "Jinx.png"),
            ("Thresh", "Thresh.png"),
        ]
        paths = download_all_champion_icons(champions)

        assert len(paths) == 3
        for path in paths:
            assert path.exists()
            assert path.suffix == ".png"

    def test_calls_progress_callback(self, monkeypatch, temp_cache_dir):
        """Progress callback is invoked with (current, total) on each download."""
        from arena_buddy.assets.icons import download_all_champion_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        progress_calls = []
        champions = [("Lucian", "Lucian.png"), ("Jinx", "Jinx.png")]

        download_all_champion_icons(
            champions, on_progress=lambda c, t: progress_calls.append((c, t))
        )

        assert progress_calls == [(1, 2), (2, 2)]

    def test_continues_on_failure(self, monkeypatch, temp_cache_dir):
        """A 404 for one champion does not prevent downloading others."""
        from arena_buddy.assets.icons import download_all_champion_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        # Jinx.png gets a 404, the others succeed
        response_map = {
            "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Lucian.png": _fake_response(),
            "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Jinx.png": _fake_response(status_code=404),
            "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Thresh.png": _fake_response(),
        }
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(response_map=response_map),
        )

        champions = [
            ("Lucian", "Lucian.png"),
            ("Jinx", "Jinx.png"),
            ("Thresh", "Thresh.png"),
        ]
        paths = download_all_champion_icons(champions)

        # Only 2 successful downloads
        assert len(paths) == 2
        names = {p.stem for p in paths}
        assert names == {"Lucian", "Thresh"}

    def test_empty_list_returns_empty(self, monkeypatch, temp_cache_dir):
        """Empty champion list returns an empty list without network calls."""
        from arena_buddy.assets.icons import download_all_champion_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        paths = download_all_champion_icons([])
        assert paths == []
        mock_client.get.assert_not_called()


class TestDownloadAllItemIcons:
    """Tests for download_all_item_icons()."""

    def test_downloads_multiple_items(self, monkeypatch, temp_cache_dir):
        """Downloads icons for a list of item IDs."""
        from arena_buddy.assets.icons import download_all_item_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        items = [1001, 1004, 1006]
        paths = download_all_item_icons(items)

        assert len(paths) == 3
        for path in paths:
            assert path.exists()

    def test_calls_progress_callback(self, monkeypatch, temp_cache_dir):
        """Progress callback fires for item batch downloads."""
        from arena_buddy.assets.icons import download_all_item_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        progress_calls = []
        items = [1001, 1004]
        download_all_item_icons(items, on_progress=lambda c, t: progress_calls.append((c, t)))

        assert progress_calls == [(1, 2), (2, 2)]

    def test_continues_on_failure(self, monkeypatch, temp_cache_dir):
        """Network error for one item doesn't crash the batch."""
        from arena_buddy.assets.icons import download_all_item_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        response_map = {
            "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/item/1001.png": _fake_response(),
            "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/item/1004.png": _fake_response(status_code=500),
            "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/item/1006.png": _fake_response(),
        }
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(response_map=response_map),
        )

        paths = download_all_item_icons([1001, 1004, 1006])
        assert len(paths) == 2


class TestDownloadAllAugmentIcons:
    """Tests for download_all_augment_icons()."""

    def test_downloads_multiple_augments(self, monkeypatch, temp_cache_dir):
        """Downloads icons for a list of augment apiNames."""
        from arena_buddy.assets.icons import download_all_augment_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        augments = ["WarmupRoutine", "BackToBasics", "BladeWaltz"]
        paths = download_all_augment_icons(augments)

        assert len(paths) == 3
        for path in paths:
            assert path.exists()

    def test_calls_progress_callback(self, monkeypatch, temp_cache_dir):
        """Progress callback fires for augment batch downloads."""
        from arena_buddy.assets.icons import download_all_augment_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        progress_calls = []
        augments = ["WarmupRoutine", "BackToBasics"]
        download_all_augment_icons(
            augments, on_progress=lambda c, t: progress_calls.append((c, t))
        )

        assert progress_calls == [(1, 2), (2, 2)]

    def test_continues_on_failure(self, monkeypatch, temp_cache_dir):
        """A failed augment download doesn't stop the batch."""
        from arena_buddy.assets.icons import download_all_augment_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        # BackToBasics gets a 404
        response_map = {
            "https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons/warmuproutine_large.png": _fake_response(),
            "https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons/backtobasics_large.png": _fake_response(status_code=404),
            "https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons/bladewaltz_large.png": _fake_response(),
        }
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(response_map=response_map),
        )

        paths = download_all_augment_icons(["WarmupRoutine", "BackToBasics", "BladeWaltz"])
        assert len(paths) == 2


# ---------------------------------------------------------------------------
# Test URL correctness
# ---------------------------------------------------------------------------

class TestUrlConstruction:
    """Verify the correct CDN URLs are used."""

    def test_champion_url(self, monkeypatch, temp_cache_dir):
        """Champion icon URL uses Data Dragon base."""
        from arena_buddy.assets.icons import download_champion_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        download_champion_icon("Aatrox", "Aatrox.png")
        mock_client.get.assert_called_once()
        url = mock_client.get.call_args[0][0]
        assert url == "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Aatrox.png"

    def test_item_url(self, monkeypatch, temp_cache_dir):
        """Item icon URL uses Data Dragon base."""
        from arena_buddy.assets.icons import download_item_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        download_item_icon(3153)
        mock_client.get.assert_called_once()
        url = mock_client.get.call_args[0][0]
        assert url == "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/item/3153.png"

    def test_augment_url(self, monkeypatch, temp_cache_dir):
        """Augment icon URL uses CommunityDragon base."""
        from arena_buddy.assets.icons import download_augment_icon

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        download_augment_icon("SymphonyOfWar")
        mock_client.get.assert_called_once()
        url = mock_client.get.call_args[0][0]
        assert url == (
            "https://raw.communitydragon.org/latest/game/assets/ux/cherry/augments/icons/"
            "symphonyofwar_large.png"
        )


# ---------------------------------------------------------------------------
# Test retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """Tests for httpx retry transport configuration."""

    def test_client_uses_retry_transport(self, monkeypatch):
        """The httpx client is created with an HTTPTransport that has retries."""
        from arena_buddy.assets.icons import _get_client

        # Patch HTTPTransport to verify it receives retries parameter
        import arena_buddy.assets.icons as icons_mod
        original = icons_mod.httpx.HTTPTransport

        calls = []

        class FakeTransport(original):
            def __init__(self, **kwargs):
                calls.append(kwargs)
                super().__init__(**kwargs)

        monkeypatch.setattr(icons_mod.httpx, "HTTPTransport", FakeTransport)

        client = _get_client()
        client.close()

        assert len(calls) >= 1
        # The transport should have retries configured
        assert calls[0].get("retries", 0) > 0


# ---------------------------------------------------------------------------
# Test network failure resilience
# ---------------------------------------------------------------------------

class TestNetworkFailureResilience:
    """Batch operations survive network-level failures."""

    def test_connection_error_does_not_crash_batch(self, monkeypatch, temp_cache_dir):
        """A connection error on one champion skips it and continues."""
        from arena_buddy.assets.icons import download_all_champion_icons

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        # Use a module-level call counter so the *second* HTTP request fails
        # regardless of which Client instance handles it.
        call_counter = 0

        class FailingClient:
            def __init__(self, *args, **kwargs):
                self.get = MagicMock()

            def _get_side_effect(self, url, **kwargs):
                nonlocal call_counter
                call_counter += 1
                if call_counter == 2:
                    raise httpx.ConnectError("Connection refused")
                return _fake_response(url=url)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def client_factory(*args, **kwargs):
            c = FailingClient()
            c.get.side_effect = c._get_side_effect
            return c

        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client", client_factory
        )

        champions = [
            ("Lucian", "Lucian.png"),
            ("Jinx", "Jinx.png"),     # this one will fail
            ("Thresh", "Thresh.png"),
        ]
        paths = download_all_champion_icons(champions)

        # Only 2 successful downloads, no crash
        assert len(paths) == 2


# ---------------------------------------------------------------------------
# Test ensure_icons_for_champion
# ---------------------------------------------------------------------------

class TestEnsureIconsForChampion:
    """Tests for ensure_icons_for_champion() — lazy icon download."""

    def test_downloads_all_types(self, monkeypatch, temp_cache_dir):
        """Downloads champion, item, and augment icons."""
        from arena_buddy.assets.icons import ensure_icons_for_champion

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        result = ensure_icons_for_champion(
            champion_key="Lucian",
            champion_icon="Lucian.png",
            item_ids=[1001, 1004],
            augment_api_names=["BackToBasics", "WarmupRoutine"],
        )

        assert result["champion"] == 1
        assert result["item"] == 2
        assert result["augment"] == 2
        assert result["skipped"] == 0

        # Verify files exist
        assert (temp_cache_dir / "champions" / "Lucian.png").exists()
        assert (temp_cache_dir / "items" / "1001.png").exists()
        assert (temp_cache_dir / "augments" / "BackToBasics.png").exists()

    def test_skips_existing_files(self, monkeypatch, temp_cache_dir):
        """Already-cached files are counted but not re-downloaded."""
        from arena_buddy.assets.icons import ensure_icons_for_champion

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )

        # Pre-create files
        champ_dir = temp_cache_dir / "champions"
        item_dir = temp_cache_dir / "items"
        champ_dir.mkdir(parents=True, exist_ok=True)
        item_dir.mkdir(parents=True, exist_ok=True)
        champ_dir.joinpath("Lucian.png").write_bytes(FAKE_PNG)
        item_dir.joinpath("1001.png").write_bytes(FAKE_PNG)

        mock_client = _make_mock_client()
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: mock_client,
        )

        result = ensure_icons_for_champion(
            champion_key="Lucian",
            champion_icon="Lucian.png",
            item_ids=[1001, 1004],
            augment_api_names=[],
        )

        # Champion and item 1001 already cached → not re-downloaded
        # Item 1004 and augments were not pre-created → downloaded
        assert result["champion"] == 1
        assert result["item"] == 2
        assert result["skipped"] == 0

        # Client.get should only be called for the missing item (1004)
        # since champion and 1001 already exist
        call_count = mock_client.get.call_count
        assert call_count == 1, f"Expected 1 download (1004), got {call_count}"

    def test_empty_lists_return_zero(self, monkeypatch, temp_cache_dir):
        """Empty item/augment lists return zero counts with no errors."""
        from arena_buddy.assets.icons import ensure_icons_for_champion

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(),
        )

        result = ensure_icons_for_champion(
            champion_key="Lucian",
            champion_icon="Lucian.png",
            item_ids=[],
            augment_api_names=[],
        )

        assert result["champion"] == 1
        assert result["item"] == 0
        assert result["augment"] == 0
        assert result["skipped"] == 0

    def test_handles_download_failures_gracefully(self, monkeypatch, temp_cache_dir):
        """Failed downloads are counted as skipped, not raised."""
        from arena_buddy.assets.icons import ensure_icons_for_champion

        monkeypatch.setattr(
            "arena_buddy.assets.icons.get_cache_dir", lambda: temp_cache_dir
        )
        # All requests return 404
        monkeypatch.setattr(
            "arena_buddy.assets.icons.httpx.Client",
            lambda *a, **kw: _make_mock_client(default_status=404),
        )

        result = ensure_icons_for_champion(
            champion_key="Missing",
            champion_icon="Missing.png",
            item_ids=[99999],
            augment_api_names=["FakeAugment"],
        )

        # All failed → counted as skipped
        assert result["champion"] == 0
        assert result["item"] == 0
        assert result["augment"] == 0
        assert result["skipped"] == 3
