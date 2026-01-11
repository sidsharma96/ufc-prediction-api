"""Fight model - individual fight matchups."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.event import Event
    from app.db.models.fighter import Fighter
    from app.db.models.fighter_snapshot import FighterSnapshot
    from app.db.models.prediction import SystemPrediction


class Fight(Base, TimestampMixin):
    """UFC Fight model.

    Stores individual fight matchups with results and metadata.
    """

    __tablename__ = "fights"

    # Event relationship
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Fighter relationships
    fighter1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fighters.id"),
        nullable=False,
        index=True,
    )
    fighter2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fighters.id"),
        nullable=False,
        index=True,
    )

    # Fight metadata
    weight_class: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    is_title_fight: Mapped[bool] = mapped_column(Boolean, default=False)
    is_main_event: Mapped[bool] = mapped_column(Boolean, default=False)
    is_co_main_event: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_rounds: Mapped[int] = mapped_column(Integer, default=3)
    fight_order: Mapped[int | None] = mapped_column(
        Integer,
        comment="Position on card (1 = main event)",
    )

    # Result (null if not yet completed)
    winner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fighters.id"),
        nullable=True,
    )
    result_method: Mapped[str | None] = mapped_column(
        String(100),
        comment="KO/TKO, Submission, Decision (Unanimous/Split/Majority)",
    )
    result_method_detail: Mapped[str | None] = mapped_column(
        String(200),
        comment="Specific method (e.g., 'Rear Naked Choke', 'Head Kick')",
    )
    ending_round: Mapped[int | None] = mapped_column(Integer)
    ending_time: Mapped[str | None] = mapped_column(
        String(10),
        comment="Time in round (e.g., '4:32')",
    )

    # Special outcomes
    is_no_contest: Mapped[bool] = mapped_column(Boolean, default=False)
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default="scheduled",
        index=True,
        comment="scheduled, live, completed, cancelled",
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    event: Mapped["Event"] = relationship("Event", back_populates="fights")
    fighter1: Mapped["Fighter"] = relationship(
        "Fighter",
        foreign_keys=[fighter1_id],
        back_populates="fights_as_fighter1",
    )
    fighter2: Mapped["Fighter"] = relationship(
        "Fighter",
        foreign_keys=[fighter2_id],
        back_populates="fights_as_fighter2",
    )
    winner: Mapped[Optional["Fighter"]] = relationship(
        "Fighter",
        foreign_keys=[winner_id],
    )
    snapshots: Mapped[list["FighterSnapshot"]] = relationship(
        "FighterSnapshot",
        back_populates="fight",
        lazy="selectin",
    )
    system_predictions: Mapped[list["SystemPrediction"]] = relationship(
        "SystemPrediction",
        back_populates="fight",
        lazy="selectin",
    )

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "fighter1_id != fighter2_id",
            name="different_fighters",
        ),
        Index("idx_fights_event_order", "event_id", "fight_order"),
        Index("idx_fights_status_date", "status"),
        # Optimized for filtered fight queries by event and status
        Index("idx_fights_event_status", "event_id", "status"),
    )

    @property
    def is_completed(self) -> bool:
        """Check if fight has been completed."""
        return self.status == "completed"

    @property
    def is_scheduled(self) -> bool:
        """Check if fight is scheduled."""
        return self.status == "scheduled"

    @property
    def matchup(self) -> str:
        """Get fight matchup string."""
        f1 = self.fighter1.full_name if self.fighter1 else "TBA"
        f2 = self.fighter2.full_name if self.fighter2 else "TBA"
        return f"{f1} vs {f2}"

    @property
    def loser(self) -> Optional["Fighter"]:
        """Get the losing fighter."""
        if not self.winner_id or self.is_draw or self.is_no_contest:
            return None
        if self.winner_id == self.fighter1_id:
            return self.fighter2
        return self.fighter1

    @property
    def result_summary(self) -> str:
        """Get a summary of the fight result."""
        if self.status != "completed":
            return "Pending"
        if self.is_no_contest:
            return "No Contest"
        if self.is_draw:
            return "Draw"
        if self.winner and self.result_method:
            method = self.result_method
            if self.ending_round and self.ending_time:
                return f"{self.winner.last_name} via {method} (R{self.ending_round} {self.ending_time})"
            return f"{self.winner.last_name} via {method}"
        return "Unknown"

    def get_snapshot_for_fighter(
        self, fighter_id: uuid.UUID
    ) -> Optional["FighterSnapshot"]:
        """Get the pre-fight snapshot for a specific fighter."""
        for snapshot in self.snapshots:
            if snapshot.fighter_id == fighter_id:
                return snapshot
        return None

    def __repr__(self) -> str:
        return f"<Fight {self.matchup}>"
