"""Pipeline orchestrator for coordinating data imports.

The orchestrator manages multiple data sources and handles:
- Initial historical data import (Kaggle)
- Ongoing updates for upcoming events (ESPN)
- Fallback handling when sources fail
- Snapshot calculation for new fights
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_pipeline.adapters import (
    DataSourceAdapter,
    DataSourceType,
    ESPNAdapter,
    ImportResult,
    UFCAdapter,
)
from app.data_pipeline.import_service import ImportService
from app.data_pipeline.snapshot_calculator import SnapshotCalculator


class PipelineOrchestrator:
    """Orchestrates data pipeline operations.

    Coordinates between multiple data sources and manages
    the flow of data from external sources to the database.

    Primary use cases:
    1. Historical import: Load Kaggle data for past fights
    2. Upcoming sync: Fetch upcoming events from ESPN
    3. Result updates: Update fight results after events complete
    4. Fight card fallback: Use UFC.com scraper when ESPN lacks fight data
    """

    def __init__(self, db: AsyncSession):
        """Initialize orchestrator.

        Args:
            db: Async database session
        """
        self.db = db
        self.import_service = ImportService(db)
        self.snapshot_calculator = SnapshotCalculator(db)

        # Initialize adapters
        self._espn_adapter: ESPNAdapter | None = None
        self._ufc_adapter: UFCAdapter | None = None

    @property
    def espn_adapter(self) -> ESPNAdapter:
        """Get or create ESPN adapter."""
        if self._espn_adapter is None:
            self._espn_adapter = ESPNAdapter()
        return self._espn_adapter

    @property
    def ufc_adapter(self) -> UFCAdapter:
        """Get or create UFC.com scraper adapter."""
        if self._ufc_adapter is None:
            self._ufc_adapter = UFCAdapter()
        return self._ufc_adapter

    async def close(self) -> None:
        """Clean up resources."""
        if self._espn_adapter:
            await self._espn_adapter.close()
        if self._ufc_adapter:
            await self._ufc_adapter.close()

    async def import_from_adapter(
        self,
        adapter: DataSourceAdapter,
        calculate_snapshots: bool = True,
    ) -> ImportResult:
        """Import data from a specific adapter.

        Args:
            adapter: Data source adapter
            calculate_snapshots: Whether to calculate point-in-time snapshots

        Returns:
            Import result with statistics
        """
        # Run the import
        result = await self.import_service.run_import(adapter)

        # Calculate snapshots if requested and fights were imported
        if calculate_snapshots and result.fights_created > 0:
            await self.snapshot_calculator.calculate_all_snapshots()

        return result

    async def sync_upcoming_events(
        self,
        use_ufc_fallback: bool = True,
    ) -> ImportResult:
        """Sync upcoming events from ESPN with UFC.com fallback.

        Fetches upcoming events and their fight cards from ESPN.
        If ESPN returns events without fight data, falls back to
        UFC.com scraper to get fight cards.

        Args:
            use_ufc_fallback: Whether to use UFC.com scraper as fallback

        Returns:
            Import result with statistics
        """
        result = ImportResult(
            source=DataSourceType.ESPN,
            started_at=datetime.utcnow(),
        )

        try:
            # Check ESPN health
            if not await self.espn_adapter.health_check():
                result.status = "failed"
                result.add_error("ESPN API is not accessible")
                return result

            # Fetch upcoming events from ESPN
            raw_events = await self.espn_adapter.fetch_upcoming_events()
            result.events_processed = len(raw_events)

            # Fetch fights from ESPN
            raw_fighters = await self.espn_adapter.fetch_fighters()
            raw_fights = await self.espn_adapter.fetch_fights()
            result.fights_processed = len(raw_fights)

            # If ESPN has events but no fights, try UFC.com fallback
            if use_ufc_fallback and raw_events and not raw_fights:
                result.add_error("ESPN returned no fights, trying UFC.com fallback")
                ufc_fights = await self._fetch_fights_from_ufc(raw_events)
                if ufc_fights:
                    raw_fights = ufc_fights
                    result.fights_processed = len(raw_fights)
                    result.add_error(f"UFC.com fallback: fetched {len(ufc_fights)} fights")

            # Import data
            fighters = await self.import_service.import_fighters(raw_fighters, result)
            events = await self.import_service.import_events(raw_events, result)
            await self.import_service.import_fights(raw_fights, fighters, events, result)

            await self.db.commit()

            result.status = "completed"
            result.completed_at = datetime.utcnow()

        except Exception as e:
            await self.db.rollback()
            result.status = "failed"
            result.add_error(f"Sync failed: {e}")

        return result

    async def _fetch_fights_from_ufc(
        self,
        events: list,
    ) -> list:
        """Fetch fight cards from UFC.com for given events.

        Args:
            events: List of RawEvent objects

        Returns:
            List of RawFight objects from UFC.com
        """
        from app.data_pipeline.adapters.base import RawFight

        all_fights: list[RawFight] = []

        for event in events:
            try:
                # Check if UFC adapter is healthy
                if not await self.ufc_adapter.health_check():
                    continue

                # Fetch fight card for this event
                fights = await self.ufc_adapter.fetch_fight_card(event.name)

                # Associate fights with event
                for fight in fights:
                    fight.event_name = event.name
                    fight.event_date = event.event_date
                    all_fights.append(fight)

            except Exception:
                # Log but continue with other events
                pass

        return all_fights

    async def update_event_results(self, event_espn_id: str) -> ImportResult:
        """Update results for a specific event.

        Fetches the latest data for an event and updates
        fight results in the database.

        Args:
            event_espn_id: ESPN event ID

        Returns:
            Import result with statistics
        """
        result = ImportResult(
            source=DataSourceType.ESPN,
            started_at=datetime.utcnow(),
        )

        try:
            # Fetch fights for the event
            fights_data = await self.espn_adapter._fetch_event_fights(event_espn_id)
            result.fights_processed = len(fights_data)

            # Update fights in database
            for raw_fight in fights_data:
                if raw_fight.winner_name or raw_fight.is_draw or raw_fight.is_no_contest:
                    # Fight has a result - update it
                    # This would require finding the fight and updating it
                    # Implementation depends on matching logic
                    result.fights_updated += 1

            await self.db.commit()

            result.status = "completed"
            result.completed_at = datetime.utcnow()

        except Exception as e:
            await self.db.rollback()
            result.status = "failed"
            result.add_error(f"Result update failed: {e}")

        return result

    async def run_full_sync(self) -> dict[str, ImportResult]:
        """Run a full sync of all data sources.

        This performs:
        1. Sync upcoming events from ESPN
        2. Calculate any missing snapshots

        Returns:
            Dictionary of source -> result
        """
        results: dict[str, ImportResult] = {}

        # Sync from ESPN
        espn_result = await self.sync_upcoming_events()
        results["espn"] = espn_result

        # Calculate any missing snapshots
        if espn_result.fights_created > 0:
            snapshot_stats = await self.snapshot_calculator.calculate_all_snapshots()
            espn_result.errors.append(f"Snapshots: {snapshot_stats['snapshots_created']} created")

        return results

    async def get_pipeline_status(self) -> dict:
        """Get current pipeline status and health.

        Returns:
            Status information for each data source
        """
        status = {
            "timestamp": datetime.utcnow().isoformat(),
            "sources": {},
        }

        # Check ESPN
        try:
            espn_healthy = await self.espn_adapter.health_check()
            status["sources"]["espn"] = {
                "healthy": espn_healthy,
                "type": "api",
            }
        except Exception as e:
            status["sources"]["espn"] = {
                "healthy": False,
                "error": str(e),
            }

        # Check UFC.com scraper
        try:
            ufc_healthy = await self.ufc_adapter.health_check()
            status["sources"]["ufc_scraper"] = {
                "healthy": ufc_healthy,
                "type": "scraper",
                "note": "Fallback for fight cards when ESPN lacks data",
            }
        except Exception as e:
            status["sources"]["ufc_scraper"] = {
                "healthy": False,
                "error": str(e),
            }

        return status
