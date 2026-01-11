"""Integration tests for Predictions API endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestGetFightPrediction:
    """Tests for GET /api/v1/predictions/fight/{fight_id}"""

    @pytest.mark.asyncio
    async def test_get_prediction(self, client: AsyncClient, sample_fight):
        """Test getting prediction for scheduled fight."""
        response = await client.get(f"/api/v1/predictions/fight/{sample_fight.id}")
        assert response.status_code == 200
        data = response.json()
        assert "predicted_winner" in data
        assert "confidence" in data
        assert "advantage_breakdown" in data
        assert "predicted_method" in data

    @pytest.mark.asyncio
    async def test_prediction_structure(self, client: AsyncClient, sample_fight):
        """Test prediction response structure."""
        response = await client.get(f"/api/v1/predictions/fight/{sample_fight.id}")
        assert response.status_code == 200
        data = response.json()

        # Check predicted_winner structure
        assert "id" in data["predicted_winner"]
        assert "name" in data["predicted_winner"]
        assert "probability" in data["predicted_winner"]
        assert 0.5 <= data["predicted_winner"]["probability"] <= 1.0

        # Check confidence structure
        assert "score" in data["confidence"]
        assert "label" in data["confidence"]
        assert data["confidence"]["label"] in ["Low", "Medium", "High"]

        # Check advantage_breakdown structure
        breakdown = data["advantage_breakdown"]
        assert "record" in breakdown
        assert "striking" in breakdown
        assert "grappling" in breakdown
        assert "form" in breakdown
        assert "physical" in breakdown
        assert "total" in breakdown

    @pytest.mark.asyncio
    async def test_prediction_not_found(self, client: AsyncClient):
        """Test 404 for non-existent fight."""
        response = await client.get(f"/api/v1/predictions/fight/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_prediction_has_cache_headers(self, client: AsyncClient, sample_fight):
        """Test cache headers are set."""
        response = await client.get(f"/api/v1/predictions/fight/{sample_fight.id}")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers


class TestPredictMatchup:
    """Tests for POST /api/v1/predictions/matchup"""

    @pytest.mark.asyncio
    async def test_predict_matchup(self, client: AsyncClient, sample_fighters, sample_fight):
        """Test predicting hypothetical matchup."""
        response = await client.post(
            "/api/v1/predictions/matchup",
            json={
                "fighter1_id": str(sample_fighters[0].id),
                "fighter2_id": str(sample_fighters[1].id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "predicted_winner" in data
        assert "confidence" in data

    @pytest.mark.asyncio
    async def test_predict_matchup_different_fighters(
        self, client: AsyncClient, sample_fighters, sample_fight
    ):
        """Test matchup with different fighter pair."""
        response = await client.post(
            "/api/v1/predictions/matchup",
            json={
                "fighter1_id": str(sample_fighters[0].id),
                "fighter2_id": str(sample_fighters[2].id),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "predicted_winner" in data

    @pytest.mark.asyncio
    async def test_predict_matchup_invalid_fighter(self, client: AsyncClient, sample_fighters):
        """Test error for invalid fighter ID."""
        response = await client.post(
            "/api/v1/predictions/matchup",
            json={
                "fighter1_id": str(sample_fighters[0].id),
                "fighter2_id": str(uuid4()),
            },
        )
        assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    async def test_predict_matchup_missing_fields(self, client: AsyncClient):
        """Test error for missing required fields."""
        response = await client.post(
            "/api/v1/predictions/matchup", json={"fighter1_id": str(uuid4())}
        )
        assert response.status_code == 422  # Validation error


class TestUpcomingPredictions:
    """Tests for GET /api/v1/predictions/upcoming"""

    @pytest.mark.asyncio
    async def test_upcoming_predictions_empty(self, client: AsyncClient):
        """Test getting predictions when no upcoming fights."""
        response = await client.get("/api/v1/predictions/upcoming")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_upcoming_predictions(self, client: AsyncClient, sample_fight):
        """Test getting predictions for upcoming fights."""
        response = await client.get("/api/v1/predictions/upcoming")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_upcoming_predictions_limit(self, client: AsyncClient, sample_fight):
        """Test limit parameter."""
        response = await client.get("/api/v1/predictions/upcoming", params={"limit": 5})
        assert response.status_code == 200
        assert len(response.json()) <= 5

    @pytest.mark.asyncio
    async def test_upcoming_predictions_structure(self, client: AsyncClient, sample_fight):
        """Test upcoming prediction response structure."""
        response = await client.get("/api/v1/predictions/upcoming")
        assert response.status_code == 200
        data = response.json()

        if data:  # If there are predictions
            item = data[0]
            assert "fight_id" in item
            assert "fighter1_name" in item
            assert "fighter2_name" in item
            assert "predicted_winner_name" in item
            assert "win_probability" in item
            assert "confidence_label" in item


class TestAccuracyStats:
    """Tests for GET /api/v1/predictions/accuracy"""

    @pytest.mark.asyncio
    async def test_accuracy_stats_empty(self, client: AsyncClient):
        """Test getting accuracy statistics with no data."""
        response = await client.get("/api/v1/predictions/accuracy")
        assert response.status_code == 200
        data = response.json()
        assert "total_predictions" in data
        assert "accuracy" in data
        assert "by_confidence" in data

    @pytest.mark.asyncio
    async def test_accuracy_stats_structure(self, client: AsyncClient):
        """Test accuracy response structure."""
        response = await client.get("/api/v1/predictions/accuracy")
        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["total_predictions"], int)
        assert isinstance(data["correct_predictions"], int)
        assert isinstance(data["accuracy"], float)
        assert 0.0 <= data["accuracy"] <= 1.0
        assert isinstance(data["by_confidence"], dict)

    @pytest.mark.asyncio
    async def test_accuracy_stats_has_cache_headers(self, client: AsyncClient):
        """Test long cache headers are set for accuracy stats."""
        response = await client.get("/api/v1/predictions/accuracy")
        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        # Should have long cache (24h = 86400)
        cache_control = response.headers["Cache-Control"]
        assert "max-age=86400" in cache_control
