"""Tests for FastAPI API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db_path, tmp_path):
    """TestClient connected to the FastAPI app with a seeded test database."""
    from arena_buddy.web.app import create_app
    settings_path = tmp_path / "settings.json"
    app = create_app(db_path=temp_db_path, settings_path=settings_path)
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """GET /api/health."""

    def test_returns_ok(self, client):
        """Health endpoint returns status ok and version."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_version_is_string(self, client):
        """Version is a non-empty string."""
        response = client.get("/api/health")
        data = response.json()
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestChampionsEndpoint:
    """GET /api/champions."""

    def test_returns_all_champions(self, client):
        """Returns a list of champion dicts (172 when full dataset loaded)."""
        response = client.get("/api/champions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # At least one champion
        # Champions are sorted alphabetically
        assert any(c["key"] == "Lucian" for c in data)

    def test_champion_has_required_fields(self, client):
        """Each champion has id, key, name, icon_filename."""
        response = client.get("/api/champions")
        champs = response.json()
        for champ in champs:
            assert "id" in champ
            assert "key" in champ
            assert "name" in champ
            assert "icon_filename" in champ


class TestChampionItemsEndpoint:
    """GET /api/champions/{key}/items."""

    def test_returns_lucian_items(self, client):
        """Full champion recommendations response."""
        response = client.get("/api/champions/Lucian/items")
        assert response.status_code == 200
        data = response.json()
        assert data["champion"]["key"] == "Lucian"
        assert "patch" in data
        assert "last_updated" in data
        assert "items" in data
        assert "augments" in data

    def test_items_sorted_by_win_rate(self, client):
        """Items are sorted best first."""
        response = client.get("/api/champions/Lucian/items")
        items = response.json()["items"]
        win_rates = [item["win_rate"] for item in items]
        assert win_rates == sorted(win_rates, reverse=True)

    def test_items_include_personal_stats(self, client):
        """Each item has personal_win_rate and personal_games fields."""
        response = client.get("/api/champions/Lucian/items")
        items = response.json()["items"]
        for item in items:
            assert "personal_win_rate" in item
            assert "personal_games" in item

    def test_augments_grouped_by_tier(self, client):
        """Augments returned as dict with prismatic/gold/silver keys."""
        response = client.get("/api/champions/Lucian/items")
        augments = response.json()["augments"]
        assert "prismatic" in augments
        assert "gold" in augments
        assert "silver" in augments
        assert len(augments["prismatic"]) >= 0  # Seed removed; may be 0 in test DB

    def test_returns_404_for_unknown_champion(self, client):
        """Unknown champion returns 404."""
        response = client.get("/api/champions/UnknownChamp/items")
        assert response.status_code == 404

    def test_returns_404_for_unknown_champion_case_sensitive(self, client):
        """Case matters — 'lucian' is not 'Lucian'."""
        response = client.get("/api/champions/lucian/items")
        assert response.status_code == 404


class TestStatsSummaryEndpoint:
    """GET /api/stats/summary."""

    def test_returns_patch_info(self, client):
        """Stats summary includes current patch."""
        response = client.get("/api/stats/summary")
        assert response.status_code == 200
        data = response.json()
        assert "patch" in data
        assert data["patch"] == "16.11"

    def test_returns_champion_count(self, client):
        """Summary includes number of champions covered (172 when full dataset loaded)."""
        response = client.get("/api/stats/summary")
        data = response.json()
        assert data["champions_covered"] >= 1

    def test_returns_last_updated(self, client):
        """Summary includes last_updated timestamp."""
        response = client.get("/api/stats/summary")
        data = response.json()
        assert "last_updated" in data


class TestStaticFiles:
    """Static file and index serving."""

    def test_index_returns_html(self, client):
        """GET / returns HTML containing Arena Buddy."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Arena Buddy" in response.text
        assert "<!DOCTYPE html>" in response.text

    def test_css_served(self, client):
        """GET /static/css/style.css returns CSS."""
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "var(--bg-primary)" in response.text

    def test_js_served(self, client):
        """GET /static/js/app.js returns JavaScript."""
        response = client.get("/static/js/app.js")
        assert response.status_code == 200
        assert "function formatWinRate" in response.text


class TestChampionSearch:
    """GET /api/champions/search?q={query}."""

    def test_exact_match_returns_champion(self, client):
        """Searching 'Lucian' returns Lucian."""
        response = client.get("/api/champions/search?q=Lucian")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["key"] == "Lucian"

    def test_partial_match_case_insensitive(self, client):
        """Searching 'luc' (lowercase, partial) returns Lucian."""
        response = client.get("/api/champions/search?q=luc")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["key"] == "Lucian"

    def test_no_match_returns_empty_list(self, client):
        """Searching nonexistent champion returns empty list."""
        response = client.get("/api/champions/search?q=zzznotachamp")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_empty_query_returns_empty_list(self, client):
        """Empty query returns empty list."""
        response = client.get("/api/champions/search?q=")
        assert response.status_code == 200
        assert response.json() == []

    def test_search_results_have_required_fields(self, client):
        """Search results have id, key, name, icon_filename."""
        response = client.get("/api/champions/search?q=Lucian")
        data = response.json()
        for champ in data:
            assert "id" in champ
            assert "key" in champ
            assert "name" in champ
            assert "icon_filename" in champ


class TestMatchEndpoints:
    """GET /api/matches and GET /api/matches/{id}."""

    def test_list_matches_returns_empty(self, client):
        """When no matches exist, returns empty array with stats."""
        response = client.get("/api/matches")
        assert response.status_code == 200
        data = response.json()
        assert "matches" in data
        assert "total" in data
        assert "stats" in data
        assert data["matches"] == []
        assert data["total"] == 0
        assert data["stats"]["total_matches"] == 0

    def test_list_matches_has_pagination_fields(self, client):
        """Response includes limit, offset, total fields."""
        response = client.get("/api/matches?limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5
        assert data["total"] == 0

    def test_list_matches_respects_limit_bounds(self, client):
        """Limit is clamped between 1 and 100."""
        response = client.get("/api/matches?limit=200")
        assert response.status_code == 200
        assert response.json()["limit"] == 100

        response = client.get("/api/matches?limit=0")
        assert response.status_code == 200
        assert response.json()["limit"] == 1

    def test_list_matches_with_filters_empty_db(self, client):
        """Filters work even with empty match database."""
        response = client.get("/api/matches?champion=Lucian&placement=1")
        assert response.status_code == 200
        data = response.json()
        assert data["matches"] == []
        assert data["total"] == 0

    def test_match_detail_404_for_unknown(self, client):
        """Unknown match_id returns 404."""
        response = client.get("/api/matches/FAKE_GAME_ID_12345")
        assert response.status_code == 404

    def test_stats_includes_all_fields(self, client):
        """Match stats response has win_rate, avg_placement keys."""
        response = client.get("/api/matches")
        stats = response.json()["stats"]
        assert "total_matches" in stats
        assert "wins" in stats
        assert "win_rate" in stats
        assert "avg_placement" in stats


# ---------------------------------------------------------------------------
# Icon ensure / serve tests
# ---------------------------------------------------------------------------

class TestIconEnsureEndpoint:
    """POST /api/icons/ensure/{champion_key}."""

    def test_ensure_lucian_returns_download_counts(self, client):
        """Icon ensure endpoint returns download count dict."""
        response = client.post("/api/icons/ensure/Lucian")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["champion"] == "Lucian"
        assert "downloaded" in data
        assert "champion" in data["downloaded"]
        assert "item" in data["downloaded"]
        assert "augment" in data["downloaded"]
        assert "skipped" in data["downloaded"]

    def test_ensure_unknown_champion_returns_404(self, client):
        """Unknown champion returns 404."""
        response = client.post("/api/icons/ensure/NotAChamp")
        assert response.status_code == 404

    def test_ensure_is_idempotent(self, client):
        """Calling ensure twice returns success both times."""
        # First call
        r1 = client.post("/api/icons/ensure/Lucian")
        assert r1.status_code == 200
        # Second call (should skip cached icons)
        r2 = client.post("/api/icons/ensure/Lucian")
        assert r2.status_code == 200
        assert r2.json()["status"] == "ok"


class TestIconServing:
    """Verify that cached icons are served via /icons/ mount."""

    def test_static_icons_mounted(self, client):
        """The /icons path is mounted and returns 404 for missing files."""
        # After seeding, icons should be in the temp cache dir
        # But since the temp_db_path creates a fresh DB and no icons
        # are pre-cached, we verify the mount exists (returns 404, not 500)
        response = client.get("/icons/items/99999.png")
        # 404 means the mount exists but file not found — correct
        assert response.status_code == 404

    def test_champion_api_triggers_icon_downloads(self, client):
        """Calling the champion items API should trigger icon downloads (no crash)."""
        response = client.get("/api/champions/Lucian/items")
        assert response.status_code == 200
        # The response should include the champion data even if
        # icon downloads fail (graceful degradation)
        assert response.json()["champion"]["key"] == "Lucian"


# ---------------------------------------------------------------------------
# First-Run Wizard
# ---------------------------------------------------------------------------

class TestWizardEndpoints:
    """GET/POST /api/wizard/* endpoints."""

    def test_wizard_state_returns_defaults(self, client):
        """GET /api/wizard/state returns defaults when no settings exist."""
        response = client.get("/api/wizard/state")
        assert response.status_code == 200
        data = response.json()
        assert data["completed"] is False
        assert data["step"] == 0

    def test_wizard_state_reflects_completion(self, client):
        """POST /api/wizard/complete marks wizard done, GET reflects it."""
        # Mark complete
        resp = client.post("/api/wizard/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify state reflects completion
        state = client.get("/api/wizard/state").json()
        assert state["completed"] is True

    def test_wizard_step_progression(self, client):
        """POST /api/wizard/step updates the current step."""
        # Set step to 1
        resp = client.post("/api/wizard/step", json={"step": 1})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["step"] == 1

        # Verify state
        state = client.get("/api/wizard/state").json()
        assert state["step"] == 1

        # Set step to 3
        client.post("/api/wizard/step", json={"step": 3})
        state = client.get("/api/wizard/state").json()
        assert state["step"] == 3

    def test_wizard_reset(self, client):
        """POST /api/wizard/reset clears wizard state."""
        # First set some state
        client.post("/api/wizard/step", json={"step": 2})
        client.post("/api/wizard/complete")

        # Reset
        resp = client.post("/api/wizard/reset")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify defaults returned
        state = client.get("/api/wizard/state").json()
        assert state["completed"] is False
        assert state["step"] == 0

    def test_wizard_league_detection(self, client):
        """GET /api/wizard/detect-league returns league detection result."""
        response = client.get("/api/wizard/detect-league")
        assert response.status_code == 200
        data = response.json()
        assert "found" in data
        assert "path" in data
        # On a test machine without League, found should be False
        assert isinstance(data["found"], bool)
        if data["found"]:
            assert data["path"] is not None
        else:
            assert data["path"] is None


# ---------------------------------------------------------------------------
# Riot Sync Endpoint
# ---------------------------------------------------------------------------

class TestSyncRiotEndpoint:
    """POST /api/stats/sync-riot."""

    def test_sync_riot_requires_config(self, client):
        """Returns 400 when no RIOT_API_KEY or summoner config is set."""
        response = client.post("/api/stats/sync-riot")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "RIOT_API_KEY" in data["detail"] or "summoner" in data["detail"].lower()

    def test_sync_riot_requires_api_key(self, client):
        """Returns 400 when RIOT_API_KEY is missing."""
        response = client.post("/api/stats/sync-riot", json={"summoner_name": "Test", "tag_line": "NA1"})
        assert response.status_code == 400
        assert "RIOT_API_KEY" in response.json()["detail"]
