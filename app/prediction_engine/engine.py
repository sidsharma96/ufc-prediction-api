"""Main prediction engine orchestrator.

Coordinates feature extraction, prediction, and confidence scoring.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redis import CACHE_KEY_ACCURACY_STATS, get_cached, set_cached
from app.db.models import Fight, Fighter, FighterSnapshot
from app.prediction_engine.confidence import ConfidenceScorer
from app.prediction_engine.feature_extractor import FeatureExtractor, FighterFeatures
from app.prediction_engine.predictor import Prediction, RuleBasedPredictor
from app.prediction_engine.weights import PredictionWeights

# Cache TTL for accuracy stats (24 hours)
ACCURACY_CACHE_TTL = 86400


class PredictionEngine:
    """Main prediction engine for UFC fights.

    Orchestrates the prediction pipeline:
    1. Load fight and fighter data
    2. Extract features from snapshots
    3. Generate prediction with confidence scores
    4. Store prediction for tracking
    """

    def __init__(
        self,
        db: AsyncSession,
        weights: PredictionWeights | None = None,
    ):
        """Initialize prediction engine.

        Args:
            db: Async database session
            weights: Optional custom prediction weights
        """
        self.db = db
        self.feature_extractor = FeatureExtractor()
        self.predictor = RuleBasedPredictor(weights)
        self.confidence_scorer = ConfidenceScorer()

    async def predict_fight(self, fight_id: uuid.UUID) -> Prediction:
        """Generate prediction for a specific fight.

        Args:
            fight_id: UUID of the fight to predict

        Returns:
            Prediction with winner, probability, and breakdown

        Raises:
            ValueError: If fight not found or already completed
        """
        # Load fight with related data
        fight = await self._load_fight(fight_id)

        if not fight:
            raise ValueError(f"Fight {fight_id} not found")

        if fight.status == "completed":
            raise ValueError(f"Fight {fight_id} is already completed")

        if not fight.fighter1 or not fight.fighter2:
            raise ValueError(f"Fight {fight_id} missing fighter data")

        # Get features for both fighters
        f1_features = await self._get_fighter_features(fight.fighter1, fight)
        f2_features = await self._get_fighter_features(fight.fighter2, fight)

        # Generate prediction
        prediction = self.predictor.predict(
            f1_features,
            f2_features,
            fight_id=str(fight_id),
        )

        return prediction

    async def predict_matchup(
        self,
        fighter1_id: uuid.UUID,
        fighter2_id: uuid.UUID,
    ) -> Prediction:
        """Generate prediction for a hypothetical matchup.

        Args:
            fighter1_id: UUID of first fighter
            fighter2_id: UUID of second fighter

        Returns:
            Prediction for the matchup
        """
        # Load fighters
        fighter1 = await self._load_fighter(fighter1_id)
        fighter2 = await self._load_fighter(fighter2_id)

        if not fighter1:
            raise ValueError(f"Fighter {fighter1_id} not found")
        if not fighter2:
            raise ValueError(f"Fighter {fighter2_id} not found")

        # Get features using most recent snapshots
        f1_features = await self._get_fighter_features(fighter1)
        f2_features = await self._get_fighter_features(fighter2)

        return self.predictor.predict(f1_features, f2_features)

    async def predict_upcoming_fights(
        self,
        limit: int = 20,
    ) -> list[Prediction]:
        """Generate predictions for all upcoming fights.

        Args:
            limit: Maximum number of predictions to generate

        Returns:
            List of predictions for upcoming fights
        """
        # Get upcoming fights
        result = await self.db.execute(
            select(Fight)
            .where(Fight.status == "scheduled")
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.event),
            )
            .limit(limit)
        )
        fights = result.scalars().all()

        predictions = []
        for fight in fights:
            try:
                prediction = await self.predict_fight(fight.id)
                predictions.append(prediction)
            except ValueError:
                # Skip fights with missing data
                continue

        return predictions

    async def get_accuracy_stats(self, use_cache: bool = True) -> dict[str, Any]:
        """Calculate prediction accuracy statistics.

        Args:
            use_cache: Whether to use Redis cache (default True)

        Returns:
            Dictionary with accuracy metrics
        """
        # Try to get from cache first
        if use_cache:
            cached_stats = await get_cached(CACHE_KEY_ACCURACY_STATS)
            if cached_stats is not None:
                return cached_stats

        # Get completed fights that had predictions
        result = await self.db.execute(
            select(Fight)
            .where(
                Fight.status == "completed",
                Fight.winner_id.isnot(None),
            )
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.snapshots),
            )
            .limit(500)
        )
        fights = list(result.scalars().all())

        if not fights:
            return {
                "total_predictions": 0,
                "correct_predictions": 0,
                "accuracy": 0.0,
                "by_confidence": {},
            }

        # Backtest on historical fights
        correct = 0
        total = 0
        by_confidence: dict[str, dict[str, int]] = {
            "High": {"correct": 0, "total": 0},
            "Medium": {"correct": 0, "total": 0},
            "Low": {"correct": 0, "total": 0},
        }

        for fight in fights:
            try:
                # Get snapshots using O(1) lookup
                snapshot_map = {s.fighter_id: s for s in fight.snapshots}
                f1_snapshot = snapshot_map.get(fight.fighter1_id)
                f2_snapshot = snapshot_map.get(fight.fighter2_id)

                if not f1_snapshot or not f2_snapshot:
                    continue

                # Extract features and predict
                f1_features = self.feature_extractor.extract_from_snapshot(
                    f1_snapshot, fight.fighter1
                )
                f2_features = self.feature_extractor.extract_from_snapshot(
                    f2_snapshot, fight.fighter2
                )

                prediction = self.predictor.predict(f1_features, f2_features)

                # Check if correct
                total += 1
                is_correct = prediction.predicted_winner_id == str(fight.winner_id)
                if is_correct:
                    correct += 1

                # Track by confidence
                conf_label = prediction.confidence_label
                by_confidence[conf_label]["total"] += 1
                if is_correct:
                    by_confidence[conf_label]["correct"] += 1

            except Exception:
                continue

        # Calculate accuracy
        accuracy = correct / total if total > 0 else 0.0

        # Calculate per-confidence accuracy
        conf_accuracy = {}
        for label, counts in by_confidence.items():
            if counts["total"] > 0:
                conf_accuracy[label] = {
                    "accuracy": counts["correct"] / counts["total"],
                    "count": counts["total"],
                }
            else:
                conf_accuracy[label] = {"accuracy": 0.0, "count": 0}

        stats = {
            "total_predictions": total,
            "correct_predictions": correct,
            "accuracy": round(accuracy, 4),
            "by_confidence": conf_accuracy,
        }

        # Cache the computed stats
        if use_cache:
            await set_cached(CACHE_KEY_ACCURACY_STATS, stats, ACCURACY_CACHE_TTL)

        return stats

    async def _load_fight(self, fight_id: uuid.UUID) -> Fight | None:
        """Load fight with related data."""
        result = await self.db.execute(
            select(Fight)
            .where(Fight.id == fight_id)
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.event),
                selectinload(Fight.snapshots),
            )
        )
        return result.scalar_one_or_none()

    async def _load_fighter(self, fighter_id: uuid.UUID) -> Fighter | None:
        """Load fighter with snapshots."""
        result = await self.db.execute(
            select(Fighter)
            .where(Fighter.id == fighter_id)
            .options(selectinload(Fighter.snapshots))
        )
        return result.scalar_one_or_none()

    async def _get_fighter_features(
        self,
        fighter: Fighter,
        fight: Fight | None = None,
    ) -> FighterFeatures:
        """Get features for a fighter.

        Uses fight-specific snapshot if available, otherwise uses
        most recent snapshot or creates basic features.
        """
        snapshot = None

        # Try to get fight-specific snapshot using O(1) lookup
        if fight:
            fight_snapshots = getattr(fight, "snapshots", [])
            snapshot_map = {s.fighter_id: s for s in fight_snapshots}
            snapshot = snapshot_map.get(fighter.id)

        # Fallback to most recent snapshot
        if not snapshot and fighter.snapshots:
            snapshot = max(
                fighter.snapshots,
                key=lambda s: s.snapshot_date or datetime.min.date(),
            )

        if snapshot:
            return self.feature_extractor.extract_from_snapshot(snapshot, fighter)

        # No snapshot - create basic features
        return self.feature_extractor.extract_from_fighter(fighter)
