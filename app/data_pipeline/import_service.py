"""Import service for loading data into the database."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.data_pipeline.adapters.base import (
    DataSourceAdapter,
    ImportResult,
    RawEvent,
    RawFight,
    RawFighter,
)
from app.data_pipeline.transformers import (
    Deduplicator,
    EventTransformer,
    FighterTransformer,
    FightTransformer,
    normalize_name,
)
from app.db.models import DataImport, Event, Fight, Fighter
from app.repositories import EventRepository, FighterRepository, FightRepository


class ImportService:
    """Service for importing data from adapters into the database."""

    def __init__(self, db: AsyncSession):
        """Initialize import service.

        Args:
            db: Async database session
        """
        self.db = db
        self.fighter_repo = FighterRepository(db)
        self.event_repo = EventRepository(db)
        self.fight_repo = FightRepository(db)
        self.deduplicator = Deduplicator()

        # Caches for lookups during import
        self._fighter_cache: dict[str, Fighter] = {}
        self._event_cache: dict[str, Event] = {}

    async def _get_or_create_fighter(self, raw: RawFighter) -> Fighter:
        """Get existing fighter or create new one.

        Args:
            raw: Raw fighter data

        Returns:
            Fighter model instance
        """
        # Check cache first
        cache_key = normalize_name(f"{raw.first_name} {raw.last_name}")
        if cache_key in self._fighter_cache:
            return self._fighter_cache[cache_key]

        # Try to find by name
        existing = await self.fighter_repo.get_by_name(
            first_name=raw.first_name,
            last_name=raw.last_name,
        )

        if existing:
            self._fighter_cache[cache_key] = existing
            return existing

        # Create new fighter
        fighter = await self.fighter_repo.create(
            {
                "first_name": raw.first_name,
                "last_name": raw.last_name,
                "nickname": raw.nickname,
                "date_of_birth": raw.date_of_birth,
                "nationality": raw.nationality,
                "hometown": raw.hometown,
                "height_cm": raw.height_cm,
                "weight_kg": raw.weight_kg,
                "reach_cm": raw.reach_cm,
                "leg_reach_cm": raw.leg_reach_cm,
                "weight_class": raw.weight_class,
                "stance": raw.stance,
                "is_active": raw.is_active,
                "ufc_id": raw.ufc_id,
                "espn_id": raw.espn_id,
            }
        )

        self._fighter_cache[cache_key] = fighter
        return fighter

    async def _update_fighter(self, fighter: Fighter, raw: RawFighter) -> Fighter:
        """Update fighter with new data.

        Args:
            fighter: Existing fighter
            raw: Raw fighter data

        Returns:
            Updated fighter
        """
        updates = {}

        # Only update if we have new data
        if raw.nickname and not fighter.nickname:
            updates["nickname"] = raw.nickname
        if raw.date_of_birth and not fighter.date_of_birth:
            updates["date_of_birth"] = raw.date_of_birth
        if raw.nationality and not fighter.nationality:
            updates["nationality"] = raw.nationality
        if raw.hometown and not fighter.hometown:
            updates["hometown"] = raw.hometown
        if raw.height_cm and not fighter.height_cm:
            updates["height_cm"] = raw.height_cm
        if raw.weight_kg and not fighter.weight_kg:
            updates["weight_kg"] = raw.weight_kg
        if raw.reach_cm and not fighter.reach_cm:
            updates["reach_cm"] = raw.reach_cm
        if raw.stance and not fighter.stance:
            updates["stance"] = raw.stance
        if raw.ufc_id and not fighter.ufc_id:
            updates["ufc_id"] = raw.ufc_id
        if raw.espn_id and not fighter.espn_id:
            updates["espn_id"] = raw.espn_id

        if updates:
            fighter = await self.fighter_repo.update(fighter, updates)

        return fighter

    async def _get_or_create_event(self, raw: RawEvent) -> Event:
        """Get existing event or create new one.

        Args:
            raw: Raw event data

        Returns:
            Event model instance
        """
        # Check cache first
        cache_key = f"{raw.name}_{raw.event_date}"
        if cache_key in self._event_cache:
            return self._event_cache[cache_key]

        # Try to find by name and date
        existing = await self.event_repo.get_by_name_and_date(
            name=raw.name,
            event_date=raw.event_date,
        )

        if existing:
            self._event_cache[cache_key] = existing
            return existing

        # Create new event
        event = await self.event_repo.create(
            {
                "name": raw.name,
                "date": raw.event_date,
                "venue": raw.venue,
                "city": raw.city,
                "state": raw.state,
                "country": raw.country,
                "event_type": raw.event_type,
                "is_completed": raw.is_completed,
                "ufc_id": raw.ufc_id,
                "espn_id": raw.espn_id,
            }
        )

        self._event_cache[cache_key] = event
        return event

    async def _create_fight(
        self,
        raw: RawFight,
        event: Event,
        fighter1: Fighter,
        fighter2: Fighter,
        winner: Fighter | None,
    ) -> Fight:
        """Create a fight record.

        Args:
            raw: Raw fight data
            event: Event model
            fighter1: Fighter 1 model
            fighter2: Fighter 2 model
            winner: Winner model or None

        Returns:
            Fight model instance
        """
        status = "completed" if event.is_completed else "scheduled"
        if raw.is_no_contest or raw.is_draw:
            status = "completed"

        fight = await self.fight_repo.create(
            {
                "event_id": event.id,
                "fighter1_id": fighter1.id,
                "fighter2_id": fighter2.id,
                "weight_class": raw.weight_class,
                "is_title_fight": raw.is_title_fight,
                "is_main_event": raw.is_main_event,
                "scheduled_rounds": raw.scheduled_rounds,
                "fight_order": raw.fight_order,
                "winner_id": winner.id if winner else None,
                "result_method": raw.result_method,
                "result_method_detail": raw.result_method_detail,
                "ending_round": raw.ending_round,
                "ending_time": raw.ending_time,
                "is_no_contest": raw.is_no_contest,
                "is_draw": raw.is_draw,
                "status": status,
            }
        )

        return fight

    async def import_fighters(
        self,
        fighters: list[RawFighter],
        result: ImportResult,
    ) -> dict[str, Fighter]:
        """Import fighters into the database.

        Args:
            fighters: List of raw fighters to import
            result: Import result to update

        Returns:
            Dictionary mapping normalized names to Fighter models
        """
        imported: dict[str, Fighter] = {}

        # Validate and normalize
        valid_fighters = []
        for raw in fighters:
            validation = FighterTransformer.validate(raw)
            if not validation.is_valid:
                for error in validation.errors:
                    result.add_error(f"Fighter validation: {error.message}")
                continue

            normalized = FighterTransformer.normalize(raw)
            valid_fighters.append(normalized)

        # Deduplicate
        deduped = self.deduplicator.deduplicate_fighters(valid_fighters)
        result.fighters_processed = len(deduped)

        # Import
        for raw in deduped:
            try:
                cache_key = normalize_name(f"{raw.first_name} {raw.last_name}")

                # Check if exists
                existing = await self.fighter_repo.get_by_name(
                    first_name=raw.first_name,
                    last_name=raw.last_name,
                )

                if existing:
                    fighter = await self._update_fighter(existing, raw)
                    result.fighters_updated += 1
                else:
                    fighter = await self._get_or_create_fighter(raw)
                    result.fighters_created += 1

                imported[cache_key] = fighter

            except Exception as e:
                result.add_error(
                    f"Failed to import fighter {raw.first_name} {raw.last_name}: {e}"
                )

        return imported

    async def import_events(
        self,
        events: list[RawEvent],
        result: ImportResult,
    ) -> dict[str, Event]:
        """Import events into the database.

        Args:
            events: List of raw events to import
            result: Import result to update

        Returns:
            Dictionary mapping event keys to Event models
        """
        imported: dict[str, Event] = {}
        result.events_processed = len(events)

        for raw in events:
            try:
                # Validate
                validation = EventTransformer.validate(raw)
                if not validation.is_valid:
                    for error in validation.errors:
                        result.add_error(f"Event validation: {error.message}")
                    continue

                # Normalize
                normalized = EventTransformer.normalize(raw)

                # Check if exists
                existing = await self.event_repo.get_by_name_and_date(
                    name=normalized.name,
                    event_date=normalized.event_date,
                )

                if existing:
                    result.events_updated += 1
                    event = existing
                else:
                    event = await self._get_or_create_event(normalized)
                    result.events_created += 1

                cache_key = f"{normalized.name}_{normalized.event_date}"
                imported[cache_key] = event

            except Exception as e:
                result.add_error(f"Failed to import event {raw.name}: {e}")

        return imported

    async def import_fights(
        self,
        fights: list[RawFight],
        fighters: dict[str, Fighter],
        events: dict[str, Event],
        result: ImportResult,
    ) -> list[Fight]:
        """Import fights into the database.

        Args:
            fights: List of raw fights to import
            fighters: Dictionary of imported fighters
            events: Dictionary of imported events
            result: Import result to update

        Returns:
            List of imported Fight models
        """
        imported: list[Fight] = []
        result.fights_processed = len(fights)

        for raw in fights:
            try:
                # Validate
                validation = FightTransformer.validate(raw)
                if not validation.is_valid:
                    for error in validation.errors:
                        result.add_error(f"Fight validation: {error.message}")
                    continue

                # Normalize
                normalized = FightTransformer.normalize(raw)

                # Get event
                event_key = f"{normalized.event_name}_{normalized.event_date}"
                event = events.get(event_key)

                if not event and normalized.event_name and normalized.event_date:
                    # Try to create event on the fly
                    event = await self._get_or_create_event(
                        RawEvent(
                            name=normalized.event_name,
                            event_date=normalized.event_date,
                            is_completed=True,
                            source=normalized.source,
                        )
                    )
                    events[event_key] = event

                if not event:
                    result.add_error(
                        f"No event found for fight: {normalized.fighter1_name} vs "
                        f"{normalized.fighter2_name}"
                    )
                    continue

                # Get fighters
                f1_key = normalize_name(normalized.fighter1_name)
                f2_key = normalize_name(normalized.fighter2_name)

                fighter1 = fighters.get(f1_key)
                fighter2 = fighters.get(f2_key)

                # Try to get from cache or create
                if not fighter1:
                    parts = normalized.fighter1_name.split(maxsplit=1)
                    fighter1 = await self._get_or_create_fighter(
                        RawFighter(
                            first_name=parts[0] if parts else "",
                            last_name=parts[1] if len(parts) > 1 else "",
                            weight_class=normalized.weight_class,
                            source=normalized.source,
                        )
                    )
                    fighters[f1_key] = fighter1

                if not fighter2:
                    parts = normalized.fighter2_name.split(maxsplit=1)
                    fighter2 = await self._get_or_create_fighter(
                        RawFighter(
                            first_name=parts[0] if parts else "",
                            last_name=parts[1] if len(parts) > 1 else "",
                            weight_class=normalized.weight_class,
                            source=normalized.source,
                        )
                    )
                    fighters[f2_key] = fighter2

                # Determine winner
                winner: Fighter | None = None
                if normalized.winner_name:
                    winner_key = normalize_name(normalized.winner_name)
                    if winner_key == f1_key:
                        winner = fighter1
                    elif winner_key == f2_key:
                        winner = fighter2
                    else:
                        # Try name matching
                        winner = fighters.get(winner_key)

                # Check if fight already exists
                existing = await self.fight_repo.find_by_fighters_and_event(
                    fighter1_id=fighter1.id,
                    fighter2_id=fighter2.id,
                    event_id=event.id,
                )

                if existing:
                    result.fights_updated += 1
                    imported.append(existing)
                else:
                    fight = await self._create_fight(
                        normalized, event, fighter1, fighter2, winner
                    )
                    result.fights_created += 1
                    imported.append(fight)

            except Exception as e:
                result.add_error(
                    f"Failed to import fight {raw.fighter1_name} vs "
                    f"{raw.fighter2_name}: {e}"
                )

        return imported

    async def run_import(
        self,
        adapter: DataSourceAdapter,
    ) -> ImportResult:
        """Run a full import from an adapter.

        Args:
            adapter: Data source adapter to import from

        Returns:
            Import result with statistics
        """
        result = ImportResult(
            source=adapter.source_type,
            started_at=datetime.utcnow(),
        )

        # Create import record
        import_record = DataImport(
            id=uuid.uuid4(),
            source=adapter.source_type.value,
            import_type="full",
            status="running",
            started_at=result.started_at,
        )
        self.db.add(import_record)
        await self.db.flush()

        try:
            # Fetch data from adapter
            raw_fighters = await adapter.fetch_fighters()
            raw_events = await adapter.fetch_events()
            raw_fights = await adapter.fetch_fights()

            # Import in order: fighters, events, fights
            fighters = await self.import_fighters(raw_fighters, result)
            events = await self.import_events(raw_events, result)
            await self.import_fights(raw_fights, fighters, events, result)

            # Commit transaction
            await self.db.commit()

            result.status = "completed"
            result.completed_at = datetime.utcnow()

            # Update import record
            import_record.status = "completed"
            import_record.completed_at = result.completed_at
            import_record.records_processed = (
                result.fighters_processed + result.events_processed + result.fights_processed
            )
            import_record.records_created = (
                result.fighters_created + result.events_created + result.fights_created
            )
            import_record.records_updated = (
                result.fighters_updated + result.events_updated + result.fights_updated
            )
            import_record.errors = result.errors if result.errors else None

            await self.db.commit()

        except Exception as e:
            await self.db.rollback()
            result.status = "failed"
            result.add_error(f"Import failed: {e}")

            import_record.status = "failed"
            import_record.errors = result.errors
            import_record.completed_at = datetime.utcnow()

            try:
                await self.db.commit()
            except Exception:
                pass

        return result
