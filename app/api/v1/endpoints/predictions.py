"""Prediction endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.prediction import (
    AccuracyByConfidence,
    AccuracyResponse,
    AdvantageBreakdown,
    ConfidenceInfo,
    FightPredictionListItem,
    MatchupRequest,
    PredictedWinner,
    PredictionResponse,
)
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.prediction_engine import PredictionEngine

router = APIRouter(prefix="/predictions", tags=["Predictions"])


async def get_prediction_engine(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PredictionEngine:
    """Dependency to get prediction engine."""
    return PredictionEngine(db)


def prediction_to_response(prediction) -> PredictionResponse:
    """Convert engine Prediction to API response."""
    return PredictionResponse(
        fight_id=prediction.fight_id,
        predicted_winner=PredictedWinner(
            id=prediction.predicted_winner_id,
            name=prediction.predicted_winner_name,
            probability=round(prediction.win_probability, 3),
        ),
        confidence=ConfidenceInfo(
            score=round(prediction.confidence, 3),
            label=prediction.confidence_label,
        ),
        advantage_breakdown=AdvantageBreakdown(
            record=round(prediction.advantage_breakdown.record, 3),
            striking=round(prediction.advantage_breakdown.striking, 3),
            grappling=round(prediction.advantage_breakdown.grappling, 3),
            form=round(prediction.advantage_breakdown.form, 3),
            physical=round(prediction.advantage_breakdown.physical, 3),
            total=round(prediction.advantage_breakdown.total, 3),
        ),
        predicted_method=prediction.predicted_method,
        key_factors=prediction.factors[:5],
        warnings=prediction.warnings,
    )


@router.get("/fight/{fight_id}", response_model=PredictionResponse)
async def get_fight_prediction(
    fight_id: UUID,
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
) -> PredictionResponse:
    """Get prediction for a specific fight.

    Returns a detailed prediction including:
    - Predicted winner and probability
    - Confidence score and level
    - Breakdown of advantages by category
    - Key factors influencing the prediction
    """
    try:
        prediction = await engine.predict_fight(fight_id)
        return prediction_to_response(prediction)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise NotFoundException("Fight", str(fight_id))
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/matchup", response_model=PredictionResponse)
async def predict_matchup(
    request: MatchupRequest,
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
) -> PredictionResponse:
    """Predict outcome of a hypothetical matchup between two fighters.

    This endpoint allows predicting fights that don't exist in the database yet.
    Uses each fighter's most recent statistics for the prediction.
    """
    try:
        prediction = await engine.predict_matchup(
            request.fighter1_id,
            request.fighter2_id,
        )
        return prediction_to_response(prediction)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/upcoming", response_model=list[FightPredictionListItem])
async def get_upcoming_predictions(
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
    limit: int = Query(20, ge=1, le=50, description="Maximum predictions to return"),
) -> list[FightPredictionListItem]:
    """Get predictions for all upcoming scheduled fights.

    Returns a list of predictions ordered by event date.
    """
    predictions = await engine.predict_upcoming_fights(limit=limit)

    return [
        FightPredictionListItem(
            fight_id=p.fight_id or "",
            event_name="",  # Would need to join event data
            fighter1_name=p.fighter1_name,
            fighter2_name=p.fighter2_name,
            predicted_winner_name=p.predicted_winner_name,
            win_probability=round(p.win_probability, 3),
            confidence_label=p.confidence_label,
            predicted_method=p.predicted_method,
        )
        for p in predictions
    ]


@router.get("/accuracy", response_model=AccuracyResponse)
async def get_prediction_accuracy(
    engine: Annotated[PredictionEngine, Depends(get_prediction_engine)],
) -> AccuracyResponse:
    """Get prediction accuracy statistics.

    Returns overall accuracy and accuracy broken down by confidence level.
    Based on backtesting predictions against completed fights.
    """
    stats = await engine.get_accuracy_stats()

    by_confidence = {}
    for label, data in stats.get("by_confidence", {}).items():
        by_confidence[label] = AccuracyByConfidence(
            accuracy=data.get("accuracy", 0.0),
            count=data.get("count", 0),
        )

    return AccuracyResponse(
        total_predictions=stats.get("total_predictions", 0),
        correct_predictions=stats.get("correct_predictions", 0),
        accuracy=stats.get("accuracy", 0.0),
        by_confidence=by_confidence,
    )
