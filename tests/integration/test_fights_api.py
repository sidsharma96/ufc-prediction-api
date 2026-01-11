"""Integration tests for Fights API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestListFights:
    """Tests for GET /api/v1/fights"""

    @pytest.mark.asyncio
    async def test_list_fights_empty(self, client: AsyncClient):
        """Test listing fights when none exist."""
        response = await client.get("/api/v1/fights")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_fights(self, client: AsyncClient, sample_fight):
        """Test listing fights."""
        response = await client.get("/api/v1/fights")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_list_fights_pagination(self, client: AsyncClient, sample_fight):
        """Test pagination parameters."""
        response = await client.get("/api/v1/fights", params={"page": 1, "per_page": 10})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "page" in data

    @pytest.mark.asyncio
    async def test_list_fights_upcoming_filter(self, client: AsyncClient, sample_fight):
        """Test filtering upcoming fights."""
        response = await client.get("/api/v1/fights", params={"upcoming": True})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_fights_has_cache_headers(self, client: AsyncClient):
        """Test cache headers are set."""
        response = await client.get("/api/v1/fights")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestUpcomingFights:
    """Tests for GET /api/v1/fights/upcoming"""

    @pytest.mark.asyncio
    async def test_upcoming_fights_empty(self, client: AsyncClient):
        """Test getting upcoming fights when none exist."""
        response = await client.get("/api/v1/fights/upcoming")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_upcoming_fights(self, client: AsyncClient, sample_fight):
        """Test getting upcoming fights."""
        response = await client.get("/api/v1/fights/upcoming")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_upcoming_fights_limit(self, client: AsyncClient, sample_fight):
        """Test limit parameter."""
        response = await client.get("/api/v1/fights/upcoming", params={"limit": 5})
        assert response.status_code == 200
        assert len(response.json()) <= 5


class TestGetFight:
    """Tests for GET /api/v1/fights/{fight_id}"""

    @pytest.mark.asyncio
    async def test_get_fight(self, client: AsyncClient, sample_fight):
        """Test getting fight by ID."""
        response = await client.get(f"/api/v1/fights/{sample_fight.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_fight.id)
        assert "fighter1" in data
        assert "fighter2" in data
        assert "weight_class" in data

    @pytest.mark.asyncio
    async def test_get_fight_includes_snapshots(self, client: AsyncClient, sample_fight):
        """Test fight detail includes snapshots."""
        response = await client.get(f"/api/v1/fights/{sample_fight.id}")
        assert response.status_code == 200
        data = response.json()
        assert "fighter1_snapshot" in data
        assert "fighter2_snapshot" in data

    @pytest.mark.asyncio
    async def test_get_fight_not_found(self, client: AsyncClient):
        """Test 404 for non-existent fight."""
        response = await client.get(f"/api/v1/fights/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_fight_has_cache_headers(self, client: AsyncClient, sample_fight):
        """Test cache headers are set."""
        response = await client.get(f"/api/v1/fights/{sample_fight.id}")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestHeadToHead:
    """Tests for GET /api/v1/fights/head-to-head/{fighter1_id}/{fighter2_id}"""

    @pytest.mark.asyncio
    async def test_head_to_head(self, client: AsyncClient, sample_fighters):
        """Test head-to-head endpoint."""
        response = await client.get(
            f"/api/v1/fights/head-to-head/{sample_fighters[0].id}/{sample_fighters[1].id}"
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_head_to_head_with_fight(
        self, client: AsyncClient, completed_fight, sample_fighters
    ):
        """Test head-to-head with existing fight."""
        response = await client.get(
            f"/api/v1/fights/head-to-head/{sample_fighters[0].id}/{sample_fighters[1].id}"
        )
        assert response.status_code == 200
        data = response.json()
        # Should have at least the completed_fight
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_head_to_head_no_fights(self, client: AsyncClient, sample_fighters):
        """Test head-to-head when no fights exist between fighters."""
        response = await client.get(
            f"/api/v1/fights/head-to-head/{sample_fighters[0].id}/{sample_fighters[2].id}"
        )
        assert response.status_code == 200
        assert response.json() == []
