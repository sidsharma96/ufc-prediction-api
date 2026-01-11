"""Base repository with generic CRUD operations."""

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with generic CRUD operations.

    Provides common database operations for all models.
    Subclass and set `model` to use.

    Example:
        class FighterRepository(BaseRepository[Fighter]):
            model = Fighter
    """

    model: type[ModelType]

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db

    async def get(self, id: uuid.UUID) -> ModelType | None:
        """Get a single record by ID.

        Args:
            id: Record UUID

        Returns:
            Model instance or None if not found
        """
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_ids(self, ids: list[uuid.UUID]) -> Sequence[ModelType]:
        """Get multiple records by IDs.

        Args:
            ids: List of record UUIDs

        Returns:
            List of model instances
        """
        if not ids:
            return []
        result = await self.db.execute(
            select(self.model).where(self.model.id.in_(ids))
        )
        return result.scalars().all()

    async def get_all(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of model instances
        """
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def count(self, *conditions) -> int:
        """Count records with optional filter conditions.

        Args:
            *conditions: SQLAlchemy filter conditions

        Returns:
            Number of matching records
        """
        query = select(func.count()).select_from(self.model)
        if conditions:
            query = query.where(*conditions)
        result = await self.db.execute(query)
        return result.scalar_one()

    async def create(self, obj_in: dict[str, Any]) -> ModelType:
        """Create a new record.

        Args:
            obj_in: Dictionary of field values

        Returns:
            Created model instance
        """
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj

    async def create_many(self, objs_in: list[dict[str, Any]]) -> list[ModelType]:
        """Create multiple records.

        Args:
            objs_in: List of dictionaries with field values

        Returns:
            List of created model instances
        """
        db_objs = [self.model(**obj) for obj in objs_in]
        self.db.add_all(db_objs)
        await self.db.flush()
        for obj in db_objs:
            await self.db.refresh(obj)
        return db_objs

    async def update(
        self,
        db_obj: ModelType,
        obj_in: dict[str, Any],
    ) -> ModelType:
        """Update an existing record.

        Args:
            db_obj: Existing model instance
            obj_in: Dictionary of fields to update

        Returns:
            Updated model instance
        """
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        self.db.add(db_obj)
        await self.db.flush()
        await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, id: uuid.UUID) -> bool:
        """Delete a record by ID.

        Args:
            id: Record UUID

        Returns:
            True if deleted, False if not found
        """
        obj = await self.get(id)
        if obj:
            await self.db.delete(obj)
            await self.db.flush()
            return True
        return False

    async def exists(self, id: uuid.UUID) -> bool:
        """Check if a record exists.

        Args:
            id: Record UUID

        Returns:
            True if exists, False otherwise
        """
        result = await self.db.execute(
            select(func.count()).select_from(self.model).where(self.model.id == id)
        )
        return result.scalar_one() > 0
