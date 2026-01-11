"""Prediction-related Pydantic schemas."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdvantageBreakdown(BaseModel):
    """Breakdown of advantages by category."""

    model_config = ConfigDict(from_attributes=True)

    record: float = Field(description="Advantage from win rate and experience")
    striking: float = Field(description="Advantage from striking stats")
    grappling: float = Field(description="Advantage from grappling stats")
    form: float = Field(description="Advantage from recent form and momentum")
    physical: float = Field(description="Advantage from physical attributes")
    total: float = Field(description="Total advantage score")


class PredictedWinner(BaseModel):
    """Predicted winner details."""

    id: str
    name: str
    probability: float = Field(ge=0.5, le=1.0, description="Win probability")


class ConfidenceInfo(BaseModel):
    """Confidence scoring details."""

    score: float = Field(ge=0, le=1, description="Confidence score 0-1")
    label: str = Field(description="Human-readable label: Low, Medium, High")


class PredictionResponse(BaseModel):
    """Full prediction response."""

    model_config = ConfigDict(from_attributes=True)

    fight_id: str | None = None
    predicted_winner: PredictedWinner
    confidence: ConfidenceInfo
    advantage_breakdown: AdvantageBreakdown
    predicted_method: str | None = Field(
        default=None,
        description="Predicted method of victory (KO/TKO, Submission, Decision)",
    )
    key_factors: list[str] = Field(
        default_factory=list,
        description="Key factors influencing the prediction",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about prediction reliability",
    )


class MatchupRequest(BaseModel):
    """Request for hypothetical matchup prediction."""

    fighter1_id: UUID
    fighter2_id: UUID


class AccuracyByConfidence(BaseModel):
    """Accuracy stats for a confidence level."""

    accuracy: float = Field(ge=0, le=1)
    count: int = Field(ge=0)


class AccuracyResponse(BaseModel):
    """Prediction accuracy statistics."""

    total_predictions: int
    correct_predictions: int
    accuracy: float = Field(ge=0, le=1, description="Overall accuracy")
    by_confidence: dict[str, AccuracyByConfidence]


class FightPredictionListItem(BaseModel):
    """Fight with prediction for list responses."""

    fight_id: str
    event_name: str
    fighter1_name: str
    fighter2_name: str
    predicted_winner_name: str
    win_probability: float
    confidence_label: str
    predicted_method: str | None = None
