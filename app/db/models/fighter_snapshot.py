"""FighterSnapshot model - point-in-time fighter statistics.

This is the CRITICAL model for avoiding data leakage in predictions.
It captures fighter stats as they were BEFORE each fight.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.fight import Fight
    from app.db.models.fighter import Fighter


class FighterSnapshot(Base, TimestampMixin):
    """Point-in-time fighter statistics snapshot.

    This model captures all fighter statistics as they existed BEFORE
    a specific fight. This is essential for:
    1. Avoiding data leakage in ML training
    2. Historical analysis
    3. Accurate backtesting of prediction algorithms

    Each snapshot is tied to both a fighter and a specific fight,
    representing the fighter's stats going INTO that fight.
    """

    __tablename__ = "fighter_snapshots"

    # Relationships
    fighter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fighters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fights.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Snapshot date (date of the fight)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Record at time of snapshot
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    no_contests: Mapped[int] = mapped_column(Integer, default=0)

    # Striking stats (career averages up to this point)
    striking_accuracy: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Striking accuracy percentage (0-100)",
    )
    strikes_landed_per_min: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Significant strikes landed per minute",
    )
    strikes_absorbed_per_min: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Significant strikes absorbed per minute",
    )
    strike_defense: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Strike defense percentage (0-100)",
    )

    # Grappling stats
    takedown_accuracy: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Takedown accuracy percentage (0-100)",
    )
    takedown_avg_per_15min: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Takedowns averaged per 15 minutes",
    )
    takedown_defense: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Takedown defense percentage (0-100)",
    )
    submission_avg_per_15min: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Submissions averaged per 15 minutes",
    )

    # Physical attributes at time of fight
    weight_at_fight_kg: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Weight at weigh-in in kg",
    )

    # Derived stats (calculated at snapshot time)
    win_percentage: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Win percentage (0-100)",
    )
    finish_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Percentage of wins by finish (0-100)",
    )
    ko_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Percentage of wins by KO/TKO (0-100)",
    )
    submission_rate: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        comment="Percentage of wins by submission (0-100)",
    )
    avg_fight_time_seconds: Mapped[int | None] = mapped_column(
        Integer,
        comment="Average fight duration in seconds",
    )

    # Form indicators
    recent_form: Mapped[str | None] = mapped_column(
        String(20),
        comment="Last 5 fights as string (e.g., 'WWLWW')",
    )
    win_streak: Mapped[int] = mapped_column(Integer, default=0)
    loss_streak: Mapped[int] = mapped_column(Integer, default=0)
    days_since_last_fight: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    fighter: Mapped["Fighter"] = relationship(
        "Fighter",
        back_populates="snapshots",
    )
    fight: Mapped["Fight"] = relationship(
        "Fight",
        back_populates="snapshots",
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("fighter_id", "fight_id", name="uq_fighter_fight_snapshot"),
        Index("idx_snapshots_fighter_date", "fighter_id", "snapshot_date"),
    )

    @property
    def total_fights(self) -> int:
        """Get total number of fights."""
        return self.wins + self.losses + self.draws + self.no_contests

    @property
    def record(self) -> str:
        """Get record as string (e.g., '22-6-1')."""
        if self.draws > 0:
            return f"{self.wins}-{self.losses}-{self.draws}"
        return f"{self.wins}-{self.losses}"

    @property
    def strike_differential(self) -> float | None:
        """Calculate strike differential (landed - absorbed per min)."""
        if self.strikes_landed_per_min is not None and self.strikes_absorbed_per_min is not None:
            return float(self.strikes_landed_per_min) - float(self.strikes_absorbed_per_min)
        return None

    def __repr__(self) -> str:
        return f"<FighterSnapshot {self.fighter_id} @ {self.snapshot_date} ({self.record})>"
