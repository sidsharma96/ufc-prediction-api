"""System prediction repository."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.db.models import SystemPrediction
from app.repositories.base import BaseRepository


class SystemPredictionRepository(BaseRepository[SystemPrediction]):
    """Repository for SystemPrediction model operations."""

    model = SystemPrediction

    async def get_by_fight(
        self,
        fight_id: uuid.UUID,
        algorithm_version: str | None = None,
    ) -> SystemPrediction | None:
        """Get system prediction for a fight.

        Args:
            fight_id: Fight UUID
            algorithm_version: Specific algorithm version (latest if None)

        Returns:
            SystemPrediction or None
        """
        query = select(SystemPrediction).where(SystemPrediction.fight_id == fight_id)

        if algorithm_version:
            query = query.where(SystemPrediction.algorithm_version == algorithm_version)
        else:
            query = query.order_by(SystemPrediction.created_at.desc())

        query = query.limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_fight_all_versions(
        self,
        fight_id: uuid.UUID,
    ) -> Sequence[SystemPrediction]:
        """Get all system predictions for a fight (all algorithm versions).

        Args:
            fight_id: Fight UUID

        Returns:
            List of predictions
        """
        result = await self.db.execute(
            select(SystemPrediction)
            .where(SystemPrediction.fight_id == fight_id)
            .order_by(SystemPrediction.created_at.desc())
        )
        return result.scalars().all()

    async def get_accuracy_stats(
        self,
        algorithm_version: str | None = None,
    ) -> dict:
        """Get accuracy statistics for system predictions.

        Args:
            algorithm_version: Filter by algorithm version

        Returns:
            Dictionary with accuracy statistics
        """
        base_query = select(SystemPrediction).where(SystemPrediction.is_correct.isnot(None))

        if algorithm_version:
            base_query = base_query.where(SystemPrediction.algorithm_version == algorithm_version)

        # Total resolved
        total_result = await self.db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
        total = total_result.scalar_one()

        # Correct predictions
        correct_query = base_query.where(SystemPrediction.is_correct.is_(True))
        correct_result = await self.db.execute(
            select(func.count()).select_from(correct_query.subquery())
        )
        correct = correct_result.scalar_one()

        return {
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": (correct / total * 100) if total > 0 else 0,
            "algorithm_version": algorithm_version,
        }

    async def mark_result(
        self,
        prediction: SystemPrediction,
        is_correct: bool,
    ) -> SystemPrediction:
        """Mark prediction result after fight completion.

        Args:
            prediction: SystemPrediction instance
            is_correct: Whether prediction was correct

        Returns:
            Updated prediction
        """
        return await self.update(prediction, {"is_correct": is_correct})
