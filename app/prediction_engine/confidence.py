"""Confidence scoring for predictions.

Provides additional confidence metrics and calibration.
"""

from dataclasses import dataclass

from app.prediction_engine.feature_extractor import FighterFeatures


@dataclass
class ConfidenceFactors:
    """Factors affecting prediction confidence."""

    data_quality: float  # 0-1, based on available stats
    experience_level: float  # 0-1, based on fight count
    matchup_clarity: float  # 0-1, how clear the advantage is
    historical_accuracy: float  # 0-1, based on similar predictions

    @property
    def overall(self) -> float:
        """Calculate overall confidence score."""
        # Weighted average
        weights = {
            "data_quality": 0.3,
            "experience_level": 0.25,
            "matchup_clarity": 0.35,
            "historical_accuracy": 0.1,
        }
        return (
            self.data_quality * weights["data_quality"] +
            self.experience_level * weights["experience_level"] +
            self.matchup_clarity * weights["matchup_clarity"] +
            self.historical_accuracy * weights["historical_accuracy"]
        )


class ConfidenceScorer:
    """Calculates confidence scores for predictions."""

    def calculate(
        self,
        f1: FighterFeatures,
        f2: FighterFeatures,
        advantage_magnitude: float,
    ) -> ConfidenceFactors:
        """Calculate confidence factors for a prediction.

        Args:
            f1: Fighter 1 features
            f2: Fighter 2 features
            advantage_magnitude: Absolute advantage score

        Returns:
            ConfidenceFactors with component scores
        """
        return ConfidenceFactors(
            data_quality=self._assess_data_quality(f1, f2),
            experience_level=self._assess_experience(f1, f2),
            matchup_clarity=self._assess_clarity(advantage_magnitude),
            historical_accuracy=0.55,  # Default baseline
        )

    def _assess_data_quality(
        self,
        f1: FighterFeatures,
        f2: FighterFeatures,
    ) -> float:
        """Assess quality of available data."""
        score = 1.0

        # Check for missing physical attributes
        if f1.height_cm is None or f2.height_cm is None:
            score -= 0.1
        if f1.reach_cm is None or f2.reach_cm is None:
            score -= 0.1

        # Check for default/missing stats
        if f1.striking_accuracy == 0.45 or f2.striking_accuracy == 0.45:
            score -= 0.15
        if f1.takedown_defense == 0.6 or f2.takedown_defense == 0.6:
            score -= 0.1

        # Check for missing form data
        if f1.recent_form_score == 0 and f2.recent_form_score == 0:
            score -= 0.1

        return max(0.0, score)

    def _assess_experience(
        self,
        f1: FighterFeatures,
        f2: FighterFeatures,
    ) -> float:
        """Assess fighter experience levels."""
        min_fights = min(f1.total_fights, f2.total_fights)

        if min_fights >= 20:
            return 1.0
        elif min_fights >= 15:
            return 0.9
        elif min_fights >= 10:
            return 0.75
        elif min_fights >= 5:
            return 0.5
        elif min_fights >= 3:
            return 0.3
        else:
            return 0.1

    def _assess_clarity(self, advantage_magnitude: float) -> float:
        """Assess how clear the matchup advantage is."""
        # Higher advantage = clearer prediction
        if advantage_magnitude >= 0.3:
            return 1.0
        elif advantage_magnitude >= 0.2:
            return 0.8
        elif advantage_magnitude >= 0.1:
            return 0.6
        elif advantage_magnitude >= 0.05:
            return 0.4
        else:
            return 0.2
