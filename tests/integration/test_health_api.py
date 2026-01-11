"""Integration tests for Health endpoint."""

import pytest
from httpx import AsyncClient


class TestHealth:
    """Tests for GET /health"""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health endpoint returns healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "app" in data
