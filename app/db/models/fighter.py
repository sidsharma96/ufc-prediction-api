"""Fighter model - core fighter data."""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.fight import Fight
    from app.db.models.fighter_snapshot import FighterSnapshot


class Fighter(Base, TimestampMixin):
    """UFC Fighter model.

    Stores normalized fighter data with biographical information.
    """

    __tablename__ = "fighters"

    # External identifiers
    ufc_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        index=True,
        comment="UFC athlete page slug (e.g., 'conor-mcgregor')",
    )
    espn_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
        comment="ESPN fighter ID",
    )

    # Basic info
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(100))

    # Biographical data
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(100))
    hometown: Mapped[str | None] = mapped_column(String(200))

    # Physical attributes (stored in metric)
    height_cm: Mapped[float | None] = mapped_column(comment="Height in centimeters")
    weight_kg: Mapped[float | None] = mapped_column(comment="Weight in kilograms")
    reach_cm: Mapped[float | None] = mapped_column(comment="Reach in centimeters")
    leg_reach_cm: Mapped[float | None] = mapped_column(comment="Leg reach in centimeters")

    # Fighting style
    weight_class: Mapped[str | None] = mapped_column(
        String(50),
        index=True,
        comment="Primary weight class",
    )
    stance: Mapped[str | None] = mapped_column(
        String(20),
        comment="Orthodox, Southpaw, or Switch",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Media
    ufc_profile_url: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)

    # Relationships
    fights_as_fighter1: Mapped[list["Fight"]] = relationship(
        "Fight",
        foreign_keys="Fight.fighter1_id",
        back_populates="fighter1",
        lazy="selectin",
    )
    fights_as_fighter2: Mapped[list["Fight"]] = relationship(
        "Fight",
        foreign_keys="Fight.fighter2_id",
        back_populates="fighter2",
        lazy="selectin",
    )
    snapshots: Mapped[list["FighterSnapshot"]] = relationship(
        "FighterSnapshot",
        back_populates="fighter",
        lazy="selectin",
    )

    # Indexes
    __table_args__ = (
        Index("idx_fighters_name", "last_name", "first_name"),
        Index("idx_fighters_weight_class_active", "weight_class", "is_active"),
    )

    @property
    def full_name(self) -> str:
        """Get fighter's full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        """Get fighter's display name with nickname."""
        if self.nickname:
            return f'{self.first_name} "{self.nickname}" {self.last_name}'
        return self.full_name

    @property
    def height_inches(self) -> float | None:
        """Convert height to inches."""
        if self.height_cm:
            return round(self.height_cm / 2.54, 1)
        return None

    @property
    def reach_inches(self) -> float | None:
        """Convert reach to inches."""
        if self.reach_cm:
            return round(self.reach_cm / 2.54, 1)
        return None

    @property
    def all_fights(self) -> list["Fight"]:
        """Get all fights for this fighter."""
        return self.fights_as_fighter1 + self.fights_as_fighter2

    def __repr__(self) -> str:
        return f"<Fighter {self.full_name} ({self.weight_class})>"
