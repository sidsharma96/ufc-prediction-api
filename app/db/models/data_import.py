"""DataImport model - tracking data pipeline runs."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataImport(Base):
    """Data import tracking model.

    Tracks data pipeline runs for monitoring and debugging.
    """

    __tablename__ = "data_imports"

    # Import metadata
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Data source (kaggle, espn, ufc_scraper)",
    )
    import_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Import type (full, incremental, event_update)",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, running, completed, failed",
    )

    # Statistics
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Error tracking
    errors: Mapped[list | None] = mapped_column(
        JSONB,
        comment="List of errors encountered during import",
    )

    # Additional metadata
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB,
        comment="Additional import metadata",
    )

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    # Indexes
    __table_args__ = (
        Index("idx_imports_source_started", "source", "started_at"),
        Index("idx_imports_status", "status"),
    )

    @property
    def duration_seconds(self) -> float | None:
        """Calculate import duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.records_processed == 0:
            return 0.0
        successful = self.records_created + self.records_updated
        return round((successful / self.records_processed) * 100, 2)

    def __repr__(self) -> str:
        return f"<DataImport {self.source} {self.import_type} ({self.status})>"
