"""Prediction weights configuration.

Configurable weights for the rule-based prediction system.
"""

from dataclasses import dataclass


@dataclass
class PredictionWeights:
    """Weights for different prediction factors.

    All weights should sum to approximately 1.0 for interpretability.
    Higher weight = more important factor.
    """

    # Record and experience (25%)
    win_rate: float = 0.12
    experience: float = 0.08
    finish_rate: float = 0.05

    # Striking (25%)
    striking_accuracy: float = 0.08
    striking_defense: float = 0.07
    strike_differential: float = 0.10

    # Grappling (20%)
    takedown_accuracy: float = 0.06
    takedown_defense: float = 0.07
    grappling_offense: float = 0.07

    # Form and momentum (20%)
    recent_form: float = 0.10
    win_streak: float = 0.05
    activity: float = 0.05

    # Physical attributes (10%)
    reach_advantage: float = 0.05
    height_advantage: float = 0.03
    age_advantage: float = 0.02

    @classmethod
    def default(cls) -> "PredictionWeights":
        """Get default weights."""
        return cls()

    @classmethod
    def striking_focused(cls) -> "PredictionWeights":
        """Weights emphasizing striking stats."""
        return cls(
            striking_accuracy=0.12,
            striking_defense=0.10,
            strike_differential=0.15,
            takedown_accuracy=0.04,
            takedown_defense=0.05,
            grappling_offense=0.04,
        )

    @classmethod
    def grappling_focused(cls) -> "PredictionWeights":
        """Weights emphasizing grappling stats."""
        return cls(
            striking_accuracy=0.05,
            striking_defense=0.05,
            strike_differential=0.05,
            takedown_accuracy=0.10,
            takedown_defense=0.12,
            grappling_offense=0.13,
        )

    def total_weight(self) -> float:
        """Calculate total of all weights."""
        return (
            self.win_rate
            + self.experience
            + self.finish_rate
            + self.striking_accuracy
            + self.striking_defense
            + self.strike_differential
            + self.takedown_accuracy
            + self.takedown_defense
            + self.grappling_offense
            + self.recent_form
            + self.win_streak
            + self.activity
            + self.reach_advantage
            + self.height_advantage
            + self.age_advantage
        )
