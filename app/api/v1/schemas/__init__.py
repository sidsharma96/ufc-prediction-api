"""Pydantic schemas for API v1."""

from app.api.v1.schemas.common import PaginatedResponse, PaginationParams
from app.api.v1.schemas.event import (
    EventDetail,
    EventListItem,
    EventsResponse,
    FightSummary,
    UpcomingEvent,
)
from app.api.v1.schemas.fight import (
    FightDetail,
    FightListItem,
    FighterBrief,
    FighterSnapshotBrief,
    FightsResponse,
    FightWithPrediction,
    PredictionBrief,
)
from app.api.v1.schemas.fighter import (
    FighterDetail,
    FighterHistory,
    FighterListItem,
    FighterStats,
    FightersResponse,
    FighterWithStats,
    FightHistoryItem,
)
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

__all__ = [
    # Common
    "PaginatedResponse",
    "PaginationParams",
    # Events
    "EventDetail",
    "EventListItem",
    "EventsResponse",
    "FightSummary",
    "UpcomingEvent",
    # Fighters
    "FighterDetail",
    "FighterHistory",
    "FighterListItem",
    "FighterStats",
    "FightersResponse",
    "FighterWithStats",
    "FightHistoryItem",
    # Fights
    "FightDetail",
    "FightListItem",
    "FighterBrief",
    "FighterSnapshotBrief",
    "FightsResponse",
    "FightWithPrediction",
    "PredictionBrief",
    # Predictions
    "AccuracyByConfidence",
    "AccuracyResponse",
    "AdvantageBreakdown",
    "ConfidenceInfo",
    "FightPredictionListItem",
    "MatchupRequest",
    "PredictedWinner",
    "PredictionResponse",
]
