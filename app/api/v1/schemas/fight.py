"""Fight-related Pydantic schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import PaginatedResponse


class FighterBrief(BaseModel):
    """Brief fighter info for fight responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    nickname: str | None = None
    image_url: str | None = None

    @property
    def full_name(self) -> str:
        """Get fighter's full name."""
        return f"{self.first_name} {self.last_name}"


class FighterSnapshotBrief(BaseModel):
    """Brief fighter stats snapshot for fight responses."""

    model_config = ConfigDict(from_attributes=True)

    wins: int = 0
    losses: int = 0
    draws: int = 0
    win_streak: int = 0
    loss_streak: int = 0
    finish_rate: float | None = None

    @property
    def record(self) -> str:
        """Get record as string."""
        if self.draws > 0:
            return f"{self.wins}-{self.losses}-{self.draws}"
        return f"{self.wins}-{self.losses}"


class FightBase(BaseModel):
    """Base fight schema with common fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    weight_class: str
    is_title_fight: bool = False
    is_main_event: bool = False
    scheduled_rounds: int = 3
    status: str = "scheduled"


class FightListItem(FightBase):
    """Fight item for list responses."""

    event_id: UUID
    event_name: str
    event_date: date
    fighter1_name: str
    fighter2_name: str
    winner_name: str | None = None
    result_method: str | None = None


class FightDetail(FightBase):
    """Detailed fight response."""

    event_id: UUID
    event_name: str
    event_date: date
    fight_order: int | None = None
    is_co_main_event: bool = False

    # Fighters
    fighter1: FighterBrief
    fighter2: FighterBrief

    # Pre-fight snapshots (stats going into the fight)
    fighter1_snapshot: FighterSnapshotBrief | None = None
    fighter2_snapshot: FighterSnapshotBrief | None = None

    # Result (if completed)
    winner_id: UUID | None = None
    result_method: str | None = None
    result_method_detail: str | None = None
    ending_round: int | None = None
    ending_time: str | None = None
    is_no_contest: bool = False
    is_draw: bool = False

    @property
    def matchup(self) -> str:
        """Get fight matchup string."""
        return f"{self.fighter1.full_name} vs {self.fighter2.full_name}"

    @property
    def result_summary(self) -> str:
        """Get a summary of the fight result."""
        if self.status != "completed":
            return "Pending"
        if self.is_no_contest:
            return "No Contest"
        if self.is_draw:
            return "Draw"
        if self.winner_id and self.result_method:
            winner_name = (
                self.fighter1.last_name
                if self.winner_id == self.fighter1.id
                else self.fighter2.last_name
            )
            method = self.result_method
            if self.ending_round and self.ending_time:
                return f"{winner_name} via {method} (R{self.ending_round} {self.ending_time})"
            return f"{winner_name} via {method}"
        return "Unknown"


class FightWithPrediction(FightDetail):
    """Fight with system prediction."""

    prediction: "PredictionBrief | None" = None


class PredictionBrief(BaseModel):
    """Brief prediction info."""

    model_config = ConfigDict(from_attributes=True)

    predicted_winner_id: UUID
    predicted_winner_name: str
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    method_prediction: str | None = None
    reasoning: str | None = None


# Response types
FightsResponse = PaginatedResponse[FightListItem]
