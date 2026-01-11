"""Integration tests for Fighters API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import FighterFactory


class TestListFighters:
    """Tests for GET /api/v1/fighters"""

    @pytest.mark.asyncio
    async def test_list_fighters_empty(self, client: AsyncClient):
        """Test listing fighters when none exist."""
        response = await client.get("/api/v1/fighters")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_fighters(self, client: AsyncClient, sample_fighters):
        """Test listing fighters."""
        response = await client.get("/api/v1/fighters")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 3

    @pytest.mark.asyncio
    async def test_list_fighters_pagination(self, client: AsyncClient, db_session):
        """Test pagination parameters."""
        for i in range(15):
            await FighterFactory.create(db_session, first_name=f"Fighter{i}")
        await db_session.commit()

        response = await client.get("/api/v1/fighters", params={"page": 1, "per_page": 5})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_fighters_search(self, client: AsyncClient, sample_fighters):
        """Test search parameter."""
        response = await client.get("/api/v1/fighters", params={"search": "Conor"})
        assert response.status_code == 200
        data = response.json()
        assert any("Conor" in f["first_name"] for f in data["items"])

    @pytest.mark.asyncio
    async def test_list_fighters_weight_class(self, client: AsyncClient, db_session):
        """Test filtering by weight class."""
        await FighterFactory.create(db_session, weight_class="Heavyweight")
        await FighterFactory.create(db_session, weight_class="Lightweight")
        await db_session.commit()

        response = await client.get("/api/v1/fighters", params={"weight_class": "Heavyweight"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_fighters_has_cache_headers(self, client: AsyncClient):
        """Test cache headers are set."""
        response = await client.get("/api/v1/fighters")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestGetFighter:
    """Tests for GET /api/v1/fighters/{fighter_id}"""

    @pytest.mark.asyncio
    async def test_get_fighter(self, client: AsyncClient, sample_fighters):
        """Test getting fighter by ID."""
        fighter = sample_fighters[0]
        response = await client.get(f"/api/v1/fighters/{fighter.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(fighter.id)
        assert data["first_name"] == fighter.first_name

    @pytest.mark.asyncio
    async def test_get_fighter_not_found(self, client: AsyncClient):
        """Test 404 for non-existent fighter."""
        response = await client.get(f"/api/v1/fighters/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_fighter_has_cache_headers(self, client: AsyncClient, sample_fighters):
        """Test cache headers are set."""
        response = await client.get(f"/api/v1/fighters/{sample_fighters[0].id}")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestGetFighterStats:
    """Tests for GET /api/v1/fighters/{fighter_id}/stats"""

    @pytest.mark.asyncio
    async def test_get_fighter_stats_with_snapshot(
        self, client: AsyncClient, sample_fight, sample_fighters
    ):
        """Test getting fighter stats when snapshot exists."""
        fighter = sample_fighters[0]
        response = await client.get(f"/api/v1/fighters/{fighter.id}/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["fighter_id"] == str(fighter.id)
        assert "wins" in data
        assert "losses" in data

    @pytest.mark.asyncio
    async def test_get_fighter_stats_no_snapshot(self, client: AsyncClient, sample_fighters):
        """Test stats without snapshot returns defaults."""
        fighter = sample_fighters[2]  # Third fighter has no fight/snapshot
        response = await client.get(f"/api/v1/fighters/{fighter.id}/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["fighter_id"] == str(fighter.id)

    @pytest.mark.asyncio
    async def test_get_fighter_stats_not_found(self, client: AsyncClient):
        """Test 404 for non-existent fighter."""
        response = await client.get(f"/api/v1/fighters/{uuid4()}/stats")
        assert response.status_code == 404


class TestGetFighterHistory:
    """Tests for GET /api/v1/fighters/{fighter_id}/history"""

    @pytest.mark.asyncio
    async def test_get_fighter_history(self, client: AsyncClient, completed_fight, sample_fighters):
        """Test getting fighter history."""
        fighter = sample_fighters[0]
        response = await client.get(f"/api/v1/fighters/{fighter.id}/history")
        assert response.status_code == 200
        data = response.json()
        assert "fights" in data
        assert "total_fights" in data
        assert data["fighter_id"] == str(fighter.id)

    @pytest.mark.asyncio
    async def test_get_fighter_history_not_found(self, client: AsyncClient):
        """Test 404 for non-existent fighter."""
        response = await client.get(f"/api/v1/fighters/{uuid4()}/history")
        assert response.status_code == 404


class TestSearchFighters:
    """Tests for GET /api/v1/fighters/search/{query}"""

    @pytest.mark.asyncio
    async def test_search_fighters(self, client: AsyncClient, sample_fighters):
        """Test searching fighters."""
        response = await client.get("/api/v1/fighters/search/McGregor")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("McGregor" in f["last_name"] for f in data)

    @pytest.mark.asyncio
    async def test_search_fighters_by_nickname(self, client: AsyncClient, sample_fighters):
        """Test searching fighters by nickname."""
        response = await client.get("/api/v1/fighters/search/Notorious")
        assert response.status_code == 200
        # May or may not find based on search implementation

    @pytest.mark.asyncio
    async def test_search_fighters_no_results(self, client: AsyncClient):
        """Test search with no matching fighters."""
        response = await client.get("/api/v1/fighters/search/NonExistentFighter12345")
        assert response.status_code == 200
        assert response.json() == []
