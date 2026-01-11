"""Fighter repository."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.db.models import Fighter, FighterSnapshot
from app.repositories.base import BaseRepository


class FighterRepository(BaseRepository[Fighter]):
    """Repository for Fighter model operations."""

    model = Fighter

    async def get_by_ufc_id(self, ufc_id: str) -> Fighter | None:
        """Get fighter by UFC ID (slug).

        Args:
            ufc_id: UFC athlete page slug (e.g., 'conor-mcgregor')

        Returns:
            Fighter instance or None
        """
        result = await self.db.execute(select(Fighter).where(Fighter.ufc_id == ufc_id))
        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        first_name: str,
        last_name: str,
    ) -> Fighter | None:
        """Get fighter by name.

        Args:
            first_name: Fighter's first name
            last_name: Fighter's last name

        Returns:
            Fighter instance or None
        """
        result = await self.db.execute(
            select(Fighter).where(
                func.lower(Fighter.first_name) == first_name.lower(),
                func.lower(Fighter.last_name) == last_name.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        query: str,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> Sequence[Fighter]:
        """Search fighters by name.

        Args:
            query: Search query
            skip: Offset for pagination
            limit: Maximum results

        Returns:
            List of matching fighters
        """
        search_term = f"%{query.lower()}%"
        result = await self.db.execute(
            select(Fighter)
            .where(
                or_(
                    func.lower(Fighter.first_name).like(search_term),
                    func.lower(Fighter.last_name).like(search_term),
                    func.lower(Fighter.nickname).like(search_term),
                )
            )
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_weight_class(
        self,
        weight_class: str,
        *,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Fighter]:
        """Get fighters by weight class.

        Args:
            weight_class: Weight class name
            active_only: Only return active fighters
            skip: Offset for pagination
            limit: Maximum results

        Returns:
            List of fighters in weight class
        """
        query = select(Fighter).where(func.lower(Fighter.weight_class) == weight_class.lower())
        if active_only:
            query = query.where(Fighter.is_active.is_(True))
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_active_fighters(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Fighter]:
        """Get all active fighters.

        Args:
            skip: Offset for pagination
            limit: Maximum results

        Returns:
            List of active fighters
        """
        result = await self.db.execute(
            select(Fighter).where(Fighter.is_active.is_(True)).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def get_with_snapshots(
        self,
        fighter_id: uuid.UUID,
    ) -> Fighter | None:
        """Get fighter with all snapshots loaded.

        Args:
            fighter_id: Fighter UUID

        Returns:
            Fighter with snapshots or None
        """
        result = await self.db.execute(
            select(Fighter).options(selectinload(Fighter.snapshots)).where(Fighter.id == fighter_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_snapshot(
        self,
        fighter_id: uuid.UUID,
    ) -> FighterSnapshot | None:
        """Get fighter's most recent snapshot.

        Args:
            fighter_id: Fighter UUID

        Returns:
            Latest snapshot or None
        """
        result = await self.db.execute(
            select(FighterSnapshot)
            .where(FighterSnapshot.fighter_id == fighter_id)
            .order_by(FighterSnapshot.snapshot_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_search(self, query: str) -> int:
        """Count fighters matching search query.

        Args:
            query: Search query

        Returns:
            Number of matching fighters
        """
        search_term = f"%{query.lower()}%"
        result = await self.db.execute(
            select(func.count())
            .select_from(Fighter)
            .where(
                or_(
                    func.lower(Fighter.first_name).like(search_term),
                    func.lower(Fighter.last_name).like(search_term),
                    func.lower(Fighter.nickname).like(search_term),
                )
            )
        )
        return result.scalar_one()

    async def count_by_weight_class(
        self,
        weight_class: str,
        active_only: bool = True,
    ) -> int:
        """Count fighters in weight class.

        Args:
            weight_class: Weight class name
            active_only: Only count active fighters

        Returns:
            Number of fighters in weight class
        """
        conditions = [func.lower(Fighter.weight_class) == weight_class.lower()]
        if active_only:
            conditions.append(Fighter.is_active.is_(True))
        return await self.count(*conditions)

    async def count_active(self) -> int:
        """Count active fighters.

        Returns:
            Number of active fighters
        """
        return await self.count(Fighter.is_active.is_(True))

    async def upsert_by_ufc_id(
        self,
        ufc_id: str,
        data: dict,
    ) -> Fighter:
        """Create or update fighter by UFC ID.

        Args:
            ufc_id: UFC athlete page slug
            data: Fighter data

        Returns:
            Created or updated Fighter
        """
        existing = await self.get_by_ufc_id(ufc_id)
        if existing:
            return await self.update(existing, data)
        data["ufc_id"] = ufc_id
        return await self.create(data)
