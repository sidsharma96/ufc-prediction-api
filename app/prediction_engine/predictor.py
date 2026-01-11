"""Rule-based predictor for fight outcomes.

Calculates weighted advantages between fighters to predict outcomes.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from app.prediction_engine.feature_extractor import FighterFeatures
from app.prediction_engine.weights import PredictionWeights


@dataclass
class AdvantageBreakdown:
    """Breakdown of advantages by category."""

    record: float = 0.0
    striking: float = 0.0
    grappling: float = 0.0
    form: float = 0.0
    physical: float = 0.0

    @property
    def total(self) -> float:
        """Total advantage score."""
        return self.record + self.striking + self.grappling + self.form + self.physical


@dataclass
class Prediction:
    """Fight prediction result."""

    fight_id: str | None
    fighter1_id: str
    fighter2_id: str
    fighter1_name: str
    fighter2_name: str

    # Prediction outcome
    predicted_winner_id: str
    predicted_winner_name: str
    win_probability: float  # 0.5 to 1.0

    # Confidence
    confidence: float  # 0.0 to 1.0
    confidence_label: str  # "Low", "Medium", "High"

    # Advantage breakdown
    fighter1_advantage: float  # Can be negative
    advantage_breakdown: AdvantageBreakdown = field(default_factory=AdvantageBreakdown)

    # Method prediction
    predicted_method: str | None = None
    method_probability: float | None = None

    # Metadata
    factors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "fight_id": self.fight_id,
            "predicted_winner": {
                "id": self.predicted_winner_id,
                "name": self.predicted_winner_name,
                "probability": round(self.win_probability, 3),
            },
            "confidence": {
                "score": round(self.confidence, 3),
                "label": self.confidence_label,
            },
            "advantage_breakdown": {
                "record": round(self.advantage_breakdown.record, 3),
                "striking": round(self.advantage_breakdown.striking, 3),
                "grappling": round(self.advantage_breakdown.grappling, 3),
                "form": round(self.advantage_breakdown.form, 3),
                "physical": round(self.advantage_breakdown.physical, 3),
                "total": round(self.advantage_breakdown.total, 3),
            },
            "predicted_method": self.predicted_method,
            "key_factors": self.factors[:5],
            "warnings": self.warnings,
        }


class RuleBasedPredictor:
    """Predicts fight outcomes using weighted rule-based analysis."""

    def __init__(self, weights: PredictionWeights | None = None):
        """Initialize predictor with weights.

        Args:
            weights: Optional custom weights, uses defaults if None
        """
        self.weights = weights or PredictionWeights.default()

    def predict(
        self,
        fighter1: FighterFeatures,
        fighter2: FighterFeatures,
        fight_id: str | None = None,
    ) -> Prediction:
        """Generate prediction for a fight.

        Args:
            fighter1: Features for fighter 1
            fighter2: Features for fighter 2
            fight_id: Optional fight ID

        Returns:
            Prediction with winner, probability, and breakdown
        """
        factors: list[str] = []
        warnings: list[str] = []

        # Check for data quality issues
        if fighter1.total_fights < 3:
            warnings.append(f"{fighter1.fighter_name} has limited fight history")
        if fighter2.total_fights < 3:
            warnings.append(f"{fighter2.fighter_name} has limited fight history")

        # Calculate advantages in each category
        breakdown = self._calculate_advantages(fighter1, fighter2, factors)

        # Total advantage (positive = fighter1, negative = fighter2)
        total_advantage = breakdown.total

        # Convert advantage to probability
        win_probability = self._advantage_to_probability(total_advantage)

        # Determine winner
        if total_advantage >= 0:
            winner_id = fighter1.fighter_id
            winner_name = fighter1.fighter_name
            winner_prob = win_probability
        else:
            winner_id = fighter2.fighter_id
            winner_name = fighter2.fighter_name
            winner_prob = 1.0 - win_probability

        # Calculate confidence
        confidence = self._calculate_confidence(fighter1, fighter2, abs(total_advantage))
        confidence_label = self._get_confidence_label(confidence)

        # Predict method
        predicted_method, method_prob = self._predict_method(fighter1, fighter2)

        return Prediction(
            fight_id=fight_id,
            fighter1_id=fighter1.fighter_id,
            fighter2_id=fighter2.fighter_id,
            fighter1_name=fighter1.fighter_name,
            fighter2_name=fighter2.fighter_name,
            predicted_winner_id=winner_id,
            predicted_winner_name=winner_name,
            win_probability=winner_prob,
            confidence=confidence,
            confidence_label=confidence_label,
            fighter1_advantage=total_advantage,
            advantage_breakdown=breakdown,
            predicted_method=predicted_method,
            method_probability=method_prob,
            factors=factors,
            warnings=warnings,
        )

    def _calculate_advantages(
        self,
        f1: FighterFeatures,
        f2: FighterFeatures,
        factors: list[str],
    ) -> AdvantageBreakdown:
        """Calculate weighted advantages in each category."""
        w = self.weights

        # Record advantages
        win_rate_adv = (f1.win_rate - f2.win_rate) * w.win_rate
        exp_adv = (f1.experience_score - f2.experience_score) * w.experience
        finish_adv = (f1.finish_rate - f2.finish_rate) * w.finish_rate
        record_total = win_rate_adv + exp_adv + finish_adv

        if abs(win_rate_adv) > 0.02:
            better = f1.fighter_name if win_rate_adv > 0 else f2.fighter_name
            factors.append(f"{better} has better win rate")

        # Striking advantages
        acc_adv = (f1.striking_accuracy - f2.striking_accuracy) * w.striking_accuracy
        def_adv = (f1.striking_defense - f2.striking_defense) * w.striking_defense
        diff_adv = (
            self._normalize_differential(f1.strike_differential, f2.strike_differential)
            * w.strike_differential
        )
        striking_total = acc_adv + def_adv + diff_adv

        if abs(striking_total) > 0.03:
            better = f1.fighter_name if striking_total > 0 else f2.fighter_name
            factors.append(f"{better} has striking advantage")

        # Grappling advantages
        td_acc_adv = (f1.takedown_accuracy - f2.takedown_accuracy) * w.takedown_accuracy
        td_def_adv = (f1.takedown_defense - f2.takedown_defense) * w.takedown_defense
        grap_off = (
            (
                (f1.takedowns_per_15min + f1.submissions_per_15min)
                - (f2.takedowns_per_15min + f2.submissions_per_15min)
            )
            / 10.0
            * w.grappling_offense
        )
        grappling_total = td_acc_adv + td_def_adv + grap_off

        if abs(grappling_total) > 0.03:
            better = f1.fighter_name if grappling_total > 0 else f2.fighter_name
            factors.append(f"{better} has grappling advantage")

        # Form and momentum
        form_adv = (f1.recent_form_score - f2.recent_form_score) * w.recent_form
        streak_adv = self._streak_advantage(f1, f2) * w.win_streak
        activity_adv = (f1.activity_score - f2.activity_score) * w.activity
        form_total = form_adv + streak_adv + activity_adv

        if f1.win_streak >= 3:
            factors.append(f"{f1.fighter_name} on {f1.win_streak}-fight win streak")
        elif f2.win_streak >= 3:
            factors.append(f"{f2.fighter_name} on {f2.win_streak}-fight win streak")

        # Physical advantages
        reach_adv = self._physical_advantage(f1.reach_cm, f2.reach_cm, 10.0) * w.reach_advantage
        height_adv = self._physical_advantage(f1.height_cm, f2.height_cm, 15.0) * w.height_advantage
        age_adv = self._age_advantage(f1.age_years, f2.age_years) * w.age_advantage
        physical_total = reach_adv + height_adv + age_adv

        if f1.reach_cm and f2.reach_cm:
            diff = f1.reach_cm - f2.reach_cm
            if abs(diff) >= 10:
                better = f1.fighter_name if diff > 0 else f2.fighter_name
                factors.append(f"{better} has significant reach advantage")

        return AdvantageBreakdown(
            record=record_total,
            striking=striking_total,
            grappling=grappling_total,
            form=form_total,
            physical=physical_total,
        )

    def _normalize_differential(self, diff1: float, diff2: float) -> float:
        """Normalize strike differential comparison."""
        # Scale to roughly -1 to 1 range
        return (diff1 - diff2) / 5.0

    def _streak_advantage(self, f1: FighterFeatures, f2: FighterFeatures) -> float:
        """Calculate advantage from win/loss streaks."""
        f1_streak = f1.win_streak - f1.loss_streak
        f2_streak = f2.win_streak - f2.loss_streak
        # Normalize to -1 to 1
        return (f1_streak - f2_streak) / 6.0

    def _physical_advantage(
        self,
        val1: float | None,
        val2: float | None,
        scale: float,
    ) -> float:
        """Calculate normalized physical advantage."""
        if val1 is None or val2 is None:
            return 0.0
        return (val1 - val2) / scale

    def _age_advantage(
        self,
        age1: float | None,
        age2: float | None,
    ) -> float:
        """Calculate age advantage (younger is generally better, with limits)."""
        if age1 is None or age2 is None:
            return 0.0

        # Prime age range: 28-32
        def age_score(age: float) -> float:
            if 28 <= age <= 32:
                return 1.0
            elif age < 28:
                return 0.8 + (age - 22) * 0.033
            else:
                return 1.0 - (age - 32) * 0.05

        return age_score(age1) - age_score(age2)

    def _advantage_to_probability(self, advantage: float) -> float:
        """Convert advantage score to win probability.

        Uses sigmoid-like function to map advantage to 0.5-1.0 range.
        """
        # Clamp advantage to reasonable range
        advantage = max(-1.0, min(1.0, advantage))

        # Sigmoid transformation centered at 0.5
        # advantage of 0 -> 0.5, advantage of 1 -> ~0.85
        prob = 1.0 / (1.0 + math.exp(-advantage * 3))

        return prob

    def _calculate_confidence(
        self,
        f1: FighterFeatures,
        f2: FighterFeatures,
        advantage_magnitude: float,
    ) -> float:
        """Calculate confidence in the prediction."""
        # Base confidence from advantage magnitude
        confidence = min(1.0, advantage_magnitude * 2)

        # Reduce confidence for inexperienced fighters
        min_fights = min(f1.total_fights, f2.total_fights)
        if min_fights < 5:
            confidence *= 0.6
        elif min_fights < 10:
            confidence *= 0.8

        # Reduce confidence for very close matchups
        if advantage_magnitude < 0.05:
            confidence *= 0.7

        return min(1.0, max(0.0, confidence))

    def _get_confidence_label(self, confidence: float) -> str:
        """Get human-readable confidence label."""
        if confidence >= 0.7:
            return "High"
        elif confidence >= 0.4:
            return "Medium"
        else:
            return "Low"

    def _predict_method(
        self,
        f1: FighterFeatures,
        f2: FighterFeatures,
    ) -> tuple[str | None, float | None]:
        """Predict likely method of victory."""
        # Average finish rates
        avg_ko = (f1.ko_rate + f2.ko_rate) / 2
        avg_sub = (f1.submission_rate + f2.submission_rate) / 2
        avg_finish = (f1.finish_rate + f2.finish_rate) / 2

        if avg_finish < 0.3:
            return "Decision", 0.6
        elif avg_ko > avg_sub and avg_ko > 0.3:
            return "KO/TKO", min(0.7, avg_ko + 0.2)
        elif avg_sub > 0.25:
            return "Submission", min(0.6, avg_sub + 0.15)
        else:
            return "Decision", 0.5
