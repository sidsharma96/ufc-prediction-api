"""Integration tests for Events API endpoints."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.conftest import EventFactory


class TestListEvents:
    """Tests for GET /api/v1/events"""

    @pytest.mark.asyncio
    async def test_list_events_empty(self, client: AsyncClient):
        """Test listing events when none exist."""
        response = await client.get("/api/v1/events")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_events_with_data(self, client: AsyncClient, sample_event):
        """Test listing events returns created events."""
        response = await client.get("/api/v1/events")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert any(e["name"] == "UFC 300: Test Event" for e in data["items"])

    @pytest.mark.asyncio
    async def test_list_events_pagination(self, client: AsyncClient, db_session):
        """Test pagination parameters."""
        # Create 15 events
        for i in range(15):
            await EventFactory.create(db_session, name=f"UFC Event {i}")
        await db_session.commit()

        response = await client.get("/api/v1/events", params={"page": 1, "per_page": 10})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_events_has_cache_headers(self, client: AsyncClient):
        """Test cache headers are set."""
        response = await client.get("/api/v1/events")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestUpcomingEvents:
    """Tests for GET /api/v1/events/upcoming"""

    @pytest.mark.asyncio
    async def test_upcoming_events_empty(self, client: AsyncClient):
        """Test getting upcoming events when none exist."""
        response = await client.get("/api/v1/events/upcoming")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_upcoming_events_with_data(self, client: AsyncClient, sample_event):
        """Test getting upcoming events."""
        response = await client.get("/api/v1/events/upcoming")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_upcoming_events_limit(self, client: AsyncClient, db_session):
        """Test limit parameter."""
        for i in range(10):
            await EventFactory.create(
                db_session, name=f"UFC {i}", date=date.today() + timedelta(days=i + 1)
            )
        await db_session.commit()

        response = await client.get("/api/v1/events/upcoming", params={"limit": 3})
        assert response.status_code == 200
        assert len(response.json()) <= 3


class TestGetEvent:
    """Tests for GET /api/v1/events/{event_id}"""

    @pytest.mark.asyncio
    async def test_get_event_exists(self, client: AsyncClient, sample_event):
        """Test getting existing event."""
        response = await client.get(f"/api/v1/events/{sample_event.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_event.id)
        assert data["name"] == sample_event.name

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, client: AsyncClient):
        """Test 404 for non-existent event."""
        response = await client.get(f"/api/v1/events/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_event_has_cache_headers(self, client: AsyncClient, sample_event):
        """Test cache headers are set."""
        response = await client.get(f"/api/v1/events/{sample_event.id}")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestSearchEvents:
    """Tests for GET /api/v1/events/search/{query}"""

    @pytest.mark.asyncio
    async def test_search_events(self, client: AsyncClient, db_session):
        """Test searching events by name."""
        await EventFactory.create(db_session, name="UFC 300: Championship Night")
        await EventFactory.create(db_session, name="UFC Fight Night: Boston")
        await db_session.commit()

        response = await client.get("/api/v1/events/search/Championship")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert all("Championship" in e["name"] for e in data)

    @pytest.mark.asyncio
    async def test_search_events_no_results(self, client: AsyncClient):
        """Test search with no matching events."""
        response = await client.get("/api/v1/events/search/NonExistentEvent12345")
        assert response.status_code == 200
        assert response.json() == []
