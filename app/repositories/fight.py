"""Fight repository."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.db.models import Event, Fight, FighterSnapshot
from app.repositories.base import BaseRepository


class FightRepository(BaseRepository[Fight]):
    """Repository for Fight model operations."""

    model = Fight

    async def get_with_details(self, fight_id: uuid.UUID) -> Fight | None:
        """Get fight with all related data loaded.

        Args:
            fight_id: Fight UUID

        Returns:
            Fight with fighters, event, and snapshots or None
        """
        result = await self.db.execute(
            select(Fight)
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.winner),
                selectinload(Fight.event),
                selectinload(Fight.snapshots),
            )
            .where(Fight.id == fight_id)
        )
        return result.scalar_one_or_none()

    async def get_by_event(
        self,
        event_id: uuid.UUID,
        *,
        include_fighters: bool = True,
    ) -> Sequence[Fight]:
        """Get all fights for an event.

        Args:
            event_id: Event UUID
            include_fighters: Whether to load fighter data

        Returns:
            List of fights ordered by fight_order
        """
        query = select(Fight).where(Fight.event_id == event_id).order_by(
            Fight.fight_order.asc()
        )

        if include_fighters:
            query = query.options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
            )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_by_fighter(
        self,
        fighter_id: uuid.UUID,
        *,
        completed_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[Fight]:
        """Get all fights for a fighter.

        Args:
            fighter_id: Fighter UUID
            completed_only: Only return completed fights
            skip: Offset for pagination
            limit: Maximum results

        Returns:
            List of fights
        """
        query = select(Fight).where(
            or_(
                Fight.fighter1_id == fighter_id,
                Fight.fighter2_id == fighter_id,
            )
        )

        if completed_only:
            query = query.where(Fight.status == "completed")

        query = (
            query.options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.event),
            )
            .order_by(Fight.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_upcoming(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[Fight]:
        """Get upcoming scheduled fights.

        Args:
            skip: Offset for pagination
            limit: Maximum results

        Returns:
            List of upcoming fights
        """
        result = await self.db.execute(
            select(Fight)
            .join(Event)
            .where(
                Fight.status == "scheduled",
                Event.date >= date.today(),
            )
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.event),
            )
            .order_by(Event.date.asc(), Fight.fight_order.asc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_all_with_details(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Fight]:
        """Get all fights with related data loaded.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of fights with fighters and events
        """
        result = await self.db.execute(
            select(Fight)
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.winner),
                selectinload(Fight.event),
            )
            .order_by(Fight.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_head_to_head(
        self,
        fighter1_id: uuid.UUID,
        fighter2_id: uuid.UUID,
    ) -> Sequence[Fight]:
        """Get all fights between two specific fighters.

        Args:
            fighter1_id: First fighter UUID
            fighter2_id: Second fighter UUID

        Returns:
            List of fights between these fighters
        """
        result = await self.db.execute(
            select(Fight)
            .where(
                or_(
                    (Fight.fighter1_id == fighter1_id)
                    & (Fight.fighter2_id == fighter2_id),
                    (Fight.fighter1_id == fighter2_id)
                    & (Fight.fighter2_id == fighter1_id),
                )
            )
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.event),
            )
            .order_by(Fight.created_at.desc())
        )
        return result.scalars().all()

    async def get_snapshots_for_fight(
        self,
        fight_id: uuid.UUID,
    ) -> Sequence[FighterSnapshot]:
        """Get fighter snapshots for a specific fight.

        Args:
            fight_id: Fight UUID

        Returns:
            List of snapshots (typically 2, one per fighter)
        """
        result = await self.db.execute(
            select(FighterSnapshot)
            .where(FighterSnapshot.fight_id == fight_id)
            .options(selectinload(FighterSnapshot.fighter))
        )
        return result.scalars().all()

    async def find_by_fighters_and_event(
        self,
        fighter1_id: uuid.UUID,
        fighter2_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> Fight | None:
        """Find a specific fight by fighters and event.

        Args:
            fighter1_id: First fighter UUID
            fighter2_id: Second fighter UUID
            event_id: Event UUID

        Returns:
            Fight or None
        """
        result = await self.db.execute(
            select(Fight).where(
                Fight.event_id == event_id,
                or_(
                    (Fight.fighter1_id == fighter1_id)
                    & (Fight.fighter2_id == fighter2_id),
                    (Fight.fighter1_id == fighter2_id)
                    & (Fight.fighter2_id == fighter1_id),
                ),
            )
        )
        return result.scalar_one_or_none()

    async def count_upcoming(self) -> int:
        """Count upcoming scheduled fights.

        Returns:
            Number of upcoming fights
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(Fight)
            .join(Event)
            .where(
                Fight.status == "scheduled",
                Event.date >= date.today(),
            )
        )
        return result.scalar_one()

    async def update_result(
        self,
        fight_id: uuid.UUID,
        winner_id: uuid.UUID | None,
        result_method: str,
        result_method_detail: str | None = None,
        ending_round: int | None = None,
        ending_time: str | None = None,
        is_no_contest: bool = False,
        is_draw: bool = False,
    ) -> Fight | None:
        """Update fight result.

        Args:
            fight_id: Fight UUID
            winner_id: Winner fighter UUID (None for NC/Draw)
            result_method: Method of victory
            result_method_detail: Specific details
            ending_round: Round fight ended
            ending_time: Time in round
            is_no_contest: Whether fight was NC
            is_draw: Whether fight was a draw

        Returns:
            Updated Fight or None if not found
        """
        fight = await self.get(fight_id)
        if not fight:
            return None

        return await self.update(
            fight,
            {
                "winner_id": winner_id,
                "result_method": result_method,
                "result_method_detail": result_method_detail,
                "ending_round": ending_round,
                "ending_time": ending_time,
                "is_no_contest": is_no_contest,
                "is_draw": is_draw,
                "status": "completed",
            },
        )
