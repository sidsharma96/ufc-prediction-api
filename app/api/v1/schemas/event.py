"""Event-related Pydantic schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import PaginatedResponse


class EventBase(BaseModel):
    """Base event schema with common fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    date: date
    venue: str | None = None
    city: str | None = None
    country: str | None = None
    is_completed: bool = False


class EventListItem(EventBase):
    """Event item for list responses."""

    event_type: str | None = None
    fight_count: int = 0
    poster_url: str | None = None

    @property
    def location(self) -> str:
        """Get formatted location string."""
        parts = [p for p in [self.city, self.country] if p]
        return ", ".join(parts) if parts else "TBA"


class FightSummary(BaseModel):
    """Brief fight summary for event detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fighter1_name: str
    fighter2_name: str
    weight_class: str
    is_title_fight: bool = False
    is_main_event: bool = False
    status: str = "scheduled"
    winner_name: str | None = None
    result_method: str | None = None


class EventDetail(EventBase):
    """Detailed event response with fights."""

    short_name: str | None = None
    event_type: str | None = None
    state: str | None = None
    start_time: datetime | None = None
    is_cancelled: bool = False
    poster_url: str | None = None
    fights: list[FightSummary] = Field(default_factory=list)

    @property
    def location(self) -> str:
        """Get formatted location string."""
        parts = [p for p in [self.city, self.state, self.country] if p]
        return ", ".join(parts) if parts else "TBA"

    @property
    def fight_count(self) -> int:
        """Get number of fights."""
        return len(self.fights)

    @property
    def main_event(self) -> FightSummary | None:
        """Get the main event fight."""
        for fight in self.fights:
            if fight.is_main_event:
                return fight
        return self.fights[0] if self.fights else None


class UpcomingEvent(EventBase):
    """Upcoming event with main event info."""

    event_type: str | None = None
    poster_url: str | None = None
    main_event_matchup: str | None = None
    fight_count: int = 0

    @property
    def location(self) -> str:
        """Get formatted location string."""
        parts = [p for p in [self.city, self.country] if p]
        return ", ".join(parts) if parts else "TBA"


# Response types
EventsResponse = PaginatedResponse[EventListItem]
