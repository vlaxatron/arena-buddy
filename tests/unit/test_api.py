"""Tests for FastAPI API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db_path):
    """TestClient connected to the FastAPI app with a seeded test database."""
    from arena_buddy.web.app import create_app
    app = create_app(db_path=temp_db_path)
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
        """Returns a list of champion dicts."""
        response = client.get("/api/champions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["key"] == "Lucian"

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
        assert len(augments["prismatic"]) == 3

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
        """Summary includes number of champions covered."""
        response = client.get("/api/stats/summary")
        data = response.json()
        assert data["champions_covered"] == 1

    def test_returns_last_updated(self, client):
        """Summary includes last_updated timestamp."""
        response = client.get("/api/stats/summary")
        data = response.json()
        assert "last_updated" in data
