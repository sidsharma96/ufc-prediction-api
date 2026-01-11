"""Event model - UFC events."""

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.fight import Fight


class Event(Base, TimestampMixin):
    """UFC Event model.

    Stores UFC event information including venue, date, and associated fights.
    """

    __tablename__ = "events"

    # External identifiers
    ufc_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="UFC event identifier",
    )
    espn_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        comment="ESPN event ID",
    )

    # Event info
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Full event name (e.g., 'UFC 300: Pereira vs. Hill')",
    )
    short_name: Mapped[str | None] = mapped_column(
        String(100),
        comment="Short name (e.g., 'UFC 300')",
    )
    event_type: Mapped[str | None] = mapped_column(
        String(50),
        comment="numbered, fight_night, apex, etc.",
    )

    # Date and time
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="Event start time with timezone",
    )

    # Location
    venue: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))

    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_cancelled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Media
    poster_url: Mapped[str | None] = mapped_column(Text)

    # Relationships
    fights: Mapped[list["Fight"]] = relationship(
        "Fight",
        back_populates="event",
        lazy="selectin",
        order_by="Fight.fight_order",
    )

    # Indexes
    __table_args__ = (
        Index("idx_events_date_completed", "date", "is_completed"),
        Index("idx_events_type_date", "event_type", "date"),
    )

    @property
    def location(self) -> str:
        """Get formatted location string."""
        parts = [p for p in [self.city, self.state, self.country] if p]
        return ", ".join(parts) if parts else "TBA"

    @property
    def main_event(self) -> Optional["Fight"]:
        """Get the main event fight."""
        for fight in self.fights:
            if fight.is_main_event:
                return fight
        # If no main event marked, return first fight (highest order)
        return self.fights[0] if self.fights else None

    @property
    def fight_count(self) -> int:
        """Get number of fights on this card."""
        return len(self.fights)

    def __repr__(self) -> str:
        return f"<Event {self.name} ({self.date})>"
