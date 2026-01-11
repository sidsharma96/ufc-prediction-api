"""Base adapter interface for data sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class DataSourceType(str, Enum):
    """Supported data source types."""

    KAGGLE = "kaggle"
    ESPN = "espn"
    UFC_SCRAPER = "ufc_scraper"


@dataclass
class RawFighter:
    """Raw fighter data from any source."""

    first_name: str
    last_name: str
    nickname: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    hometown: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    reach_cm: float | None = None
    leg_reach_cm: float | None = None
    weight_class: str | None = None
    stance: str | None = None
    is_active: bool = True

    # External IDs
    ufc_id: str | None = None
    espn_id: str | None = None

    # Stats (current/career)
    wins: int = 0
    losses: int = 0
    draws: int = 0
    no_contests: int = 0

    # Detailed stats
    ko_wins: int = 0
    submission_wins: int = 0
    decision_wins: int = 0

    # Source metadata
    source: DataSourceType | None = None
    source_url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawEvent:
    """Raw event data from any source."""

    name: str
    event_date: date
    venue: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    event_type: str | None = None  # numbered, fight_night, etc.
    is_completed: bool = False

    # External IDs
    ufc_id: str | None = None
    espn_id: str | None = None

    # Source metadata
    source: DataSourceType | None = None
    source_url: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawFight:
    """Raw fight data from any source."""

    # Required fields (must come first)
    fighter1_name: str
    fighter2_name: str
    weight_class: str

    # Event identification
    event_name: str | None = None
    event_date: date | None = None

    # Fight metadata
    is_title_fight: bool = False
    is_main_event: bool = False
    scheduled_rounds: int = 3
    fight_order: int | None = None

    # Result (None if not completed)
    winner_name: str | None = None
    result_method: str | None = None  # KO/TKO, Submission, Decision
    result_method_detail: str | None = None
    ending_round: int | None = None
    ending_time: str | None = None
    is_no_contest: bool = False
    is_draw: bool = False

    # Fighter stats at time of fight (for snapshots)
    fighter1_stats: dict[str, Any] = field(default_factory=dict)
    fighter2_stats: dict[str, Any] = field(default_factory=dict)

    # Source metadata
    source: DataSourceType | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportResult:
    """Result of a data import operation."""

    source: DataSourceType
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"  # running, completed, failed

    fighters_processed: int = 0
    fighters_created: int = 0
    fighters_updated: int = 0

    events_processed: int = 0
    events_created: int = 0
    events_updated: int = 0

    fights_processed: int = 0
    fights_created: int = 0
    fights_updated: int = 0

    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)

    @property
    def has_errors(self) -> bool:
        """Check if import had errors."""
        return len(self.errors) > 0


class DataSourceAdapter(ABC):
    """Abstract base class for data source adapters.

    All data sources (Kaggle, ESPN, UFC scraper) must implement this interface.
    """

    @property
    @abstractmethod
    def source_type(self) -> DataSourceType:
        """Return the type of this data source."""
        ...

    @abstractmethod
    async def fetch_fighters(self) -> list[RawFighter]:
        """Fetch all fighters from this data source.

        Returns:
            List of raw fighter data
        """
        ...

    @abstractmethod
    async def fetch_events(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawEvent]:
        """Fetch events from this data source.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of raw event data
        """
        ...

    @abstractmethod
    async def fetch_fights(
        self,
        event_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawFight]:
        """Fetch fights from this data source.

        Args:
            event_name: Optional event name filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of raw fight data
        """
        ...

    async def fetch_upcoming_events(self) -> list[RawEvent]:
        """Fetch upcoming events.

        Default implementation returns empty list.
        Override in adapters that support upcoming events (ESPN, UFC scraper).
        """
        return []

    async def health_check(self) -> bool:
        """Check if the data source is accessible.

        Returns:
            True if accessible, False otherwise
        """
        return True
