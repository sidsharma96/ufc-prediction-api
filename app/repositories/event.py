"""Event repository."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Event, Fight
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    """Repository for Event model operations."""

    model = Event

    async def get_by_ufc_id(self, ufc_id: str) -> Event | None:
        """Get event by UFC ID.

        Args:
            ufc_id: UFC event identifier

        Returns:
            Event instance or None
        """
        result = await self.db.execute(select(Event).where(Event.ufc_id == ufc_id))
        return result.scalar_one_or_none()

    async def get_by_name_and_date(
        self,
        name: str,
        event_date: date,
    ) -> Event | None:
        """Get event by name and date.

        Args:
            name: Event name
            event_date: Event date

        Returns:
            Event instance or None
        """
        result = await self.db.execute(
            select(Event).where(
                func.lower(Event.name) == name.lower(),
                Event.date == event_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_with_fights(self, event_id) -> Event | None:
        """Get event with all fights loaded.

        Args:
            event_id: Event UUID

        Returns:
            Event with fights or None
        """
        result = await self.db.execute(
            select(Event)
            .options(
                selectinload(Event.fights).selectinload(Fight.fighter1),
                selectinload(Event.fights).selectinload(Fight.fighter2),
            )
            .where(Event.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_upcoming(
        self,
        *,
        limit: int = 5,
        include_fights: bool = True,
    ) -> Sequence[Event]:
        """Get upcoming events.

        Args:
            limit: Maximum number of events
            include_fights: Whether to load fights

        Returns:
            List of upcoming events
        """
        query = (
            select(Event)
            .where(
                Event.is_completed.is_(False),
                Event.is_cancelled.is_(False),
                Event.date >= date.today(),
            )
            .order_by(Event.date.asc())
            .limit(limit)
        )

        if include_fights:
            query = query.options(
                selectinload(Event.fights).selectinload(Fight.fighter1),
                selectinload(Event.fights).selectinload(Fight.fighter2),
            )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_completed(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        include_fights: bool = False,
    ) -> Sequence[Event]:
        """Get completed events.

        Args:
            skip: Offset for pagination
            limit: Maximum results
            include_fights: Whether to load fights

        Returns:
            List of completed events
        """
        query = (
            select(Event)
            .where(
                Event.is_completed.is_(True),
            )
            .order_by(Event.date.desc())
            .offset(skip)
            .limit(limit)
        )

        if include_fights:
            query = query.options(
                selectinload(Event.fights).selectinload(Fight.fighter1),
                selectinload(Event.fights).selectinload(Fight.fighter2),
            )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_by_date_range(
        self,
        from_date: date,
        to_date: date,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Event]:
        """Get events within date range.

        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)
            skip: Offset for pagination
            limit: Maximum results

        Returns:
            List of events in range
        """
        result = await self.db.execute(
            select(Event)
            .where(
                Event.date >= from_date,
                Event.date <= to_date,
            )
            .order_by(Event.date.asc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def search_by_name(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> Sequence[Event]:
        """Search events by name.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            Matching events
        """
        search_term = f"%{query.lower()}%"
        result = await self.db.execute(
            select(Event)
            .where(func.lower(Event.name).like(search_term))
            .order_by(Event.date.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def count_upcoming(self) -> int:
        """Count upcoming events.

        Returns:
            Number of upcoming events
        """
        return await self.count(
            Event.is_completed.is_(False),
            Event.is_cancelled.is_(False),
            Event.date >= date.today(),
        )

    async def count_completed(self) -> int:
        """Count completed events.

        Returns:
            Number of completed events
        """
        return await self.count(Event.is_completed.is_(True))

    async def count_by_date_range(
        self,
        from_date: date,
        to_date: date,
    ) -> int:
        """Count events within date range.

        Args:
            from_date: Start date (inclusive)
            to_date: End date (inclusive)

        Returns:
            Number of events in range
        """
        return await self.count(
            Event.date >= from_date,
            Event.date <= to_date,
        )

    async def upsert_by_ufc_id(
        self,
        ufc_id: str,
        data: dict,
    ) -> Event:
        """Create or update event by UFC ID.

        Args:
            ufc_id: UFC event identifier
            data: Event data

        Returns:
            Created or updated Event
        """
        existing = await self.get_by_ufc_id(ufc_id)
        if existing:
            return await self.update(existing, data)
        data["ufc_id"] = ufc_id
        return await self.create(data)
