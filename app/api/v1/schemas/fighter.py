"""Fighter-related Pydantic schemas."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import PaginatedResponse


class FighterBase(BaseModel):
    """Base fighter schema with common fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    last_name: str
    nickname: str | None = None
    weight_class: str | None = None
    is_active: bool = True


class FighterListItem(FighterBase):
    """Fighter item for list responses."""

    nationality: str | None = None
    image_url: str | None = None

    @property
    def full_name(self) -> str:
        """Get fighter's full name."""
        return f"{self.first_name} {self.last_name}"


class FighterDetail(FighterBase):
    """Detailed fighter response."""

    date_of_birth: date | None = None
    nationality: str | None = None
    hometown: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    reach_cm: float | None = None
    leg_reach_cm: float | None = None
    stance: str | None = None
    ufc_profile_url: str | None = None
    image_url: str | None = None

    @property
    def full_name(self) -> str:
        """Get fighter's full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        """Get display name with nickname."""
        if self.nickname:
            return f'{self.first_name} "{self.nickname}" {self.last_name}'
        return self.full_name

    @property
    def age(self) -> int | None:
        """Calculate current age."""
        if self.date_of_birth:
            today = date.today()
            return (
                today.year
                - self.date_of_birth.year
                - (
                    (today.month, today.day)
                    < (self.date_of_birth.month, self.date_of_birth.day)
                )
            )
        return None


class FighterStats(BaseModel):
    """Fighter statistics schema."""

    model_config = ConfigDict(from_attributes=True)

    fighter_id: UUID
    wins: int = 0
    losses: int = 0
    draws: int = 0
    no_contests: int = 0
    win_streak: int = 0
    loss_streak: int = 0
    finish_rate: float | None = None
    ko_rate: float | None = None
    submission_rate: float | None = None
    striking_accuracy: float | None = None
    takedown_accuracy: float | None = None
    takedown_defense: float | None = None
    strike_defense: float | None = None

    @property
    def record(self) -> str:
        """Get record as string (e.g., '22-6-1')."""
        if self.draws > 0:
            return f"{self.wins}-{self.losses}-{self.draws}"
        return f"{self.wins}-{self.losses}"

    @property
    def total_fights(self) -> int:
        """Get total number of fights."""
        return self.wins + self.losses + self.draws + self.no_contests


class FighterWithStats(FighterDetail):
    """Fighter with current statistics."""

    stats: FighterStats | None = None


class FightHistoryItem(BaseModel):
    """Single fight in fighter's history."""

    model_config = ConfigDict(from_attributes=True)

    fight_id: UUID
    event_name: str
    event_date: date
    opponent_name: str
    opponent_id: UUID
    weight_class: str
    result: str = Field(description="Win, Loss, Draw, or No Contest")
    method: str | None = None
    ending_round: int | None = None
    ending_time: str | None = None
    is_title_fight: bool = False
    is_main_event: bool = False


class FighterHistory(BaseModel):
    """Fighter's complete fight history."""

    fighter_id: UUID
    fighter_name: str
    fights: list[FightHistoryItem]
    total_fights: int


# Response types
FightersResponse = PaginatedResponse[FighterListItem]
