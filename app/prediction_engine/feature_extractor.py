"""Feature extractor for fight predictions.

Extracts normalized features from fighter snapshots for use in prediction.
"""

from dataclasses import dataclass, field
from typing import Any

from app.db.models import Fighter, FighterSnapshot


@dataclass
class FighterFeatures:
    """Extracted features for a single fighter."""
    
    fighter_id: str
    fighter_name: str
    
    # Record features (0-1 normalized)
    win_rate: float = 0.0
    finish_rate: float = 0.0
    ko_rate: float = 0.0
    submission_rate: float = 0.0
    
    # Experience
    total_fights: int = 0
    experience_score: float = 0.0
    
    # Striking features
    striking_accuracy: float = 0.0
    striking_defense: float = 0.0
    strikes_per_min: float = 0.0
    strikes_absorbed_per_min: float = 0.0
    strike_differential: float = 0.0
    
    # Grappling features
    takedown_accuracy: float = 0.0
    takedown_defense: float = 0.0
    takedowns_per_15min: float = 0.0
    submissions_per_15min: float = 0.0
    
    # Form and momentum
    win_streak: int = 0
    loss_streak: int = 0
    recent_form_score: float = 0.0
    days_since_fight: int | None = None
    activity_score: float = 0.0
    
    # Physical attributes
    height_cm: float | None = None
    reach_cm: float | None = None
    age_years: float | None = None
    
    raw_data: dict[str, Any] = field(default_factory=dict)


class FeatureExtractor:
    """Extracts normalized features from fighter data."""
    
    MAX_FIGHTS_FOR_EXPERIENCE = 40
    MAX_DAYS_FOR_ACTIVITY = 730
    
    def extract_from_snapshot(
        self,
        snapshot: FighterSnapshot,
        fighter: Fighter | None = None,
    ) -> FighterFeatures:
        """Extract features from a fighter snapshot."""
        if fighter is None:
            fighter = snapshot.fighter
        
        total_fights = snapshot.wins + snapshot.losses + snapshot.draws
        win_rate = snapshot.wins / total_fights if total_fights > 0 else 0.5
        
        finish_rate = self._safe_float(snapshot.finish_rate, 0.0) / 100.0
        ko_rate = self._safe_float(snapshot.ko_rate, 0.0) / 100.0
        submission_rate = self._safe_float(snapshot.submission_rate, 0.0) / 100.0
        
        experience_score = min(1.0, total_fights / self.MAX_FIGHTS_FOR_EXPERIENCE)
        
        striking_accuracy = self._safe_float(snapshot.striking_accuracy, 45.0) / 100.0
        striking_defense = self._safe_float(snapshot.strike_defense, 55.0) / 100.0
        strikes_per_min = self._safe_float(snapshot.strikes_landed_per_min, 3.0)
        strikes_absorbed = self._safe_float(snapshot.strikes_absorbed_per_min, 3.0)
        strike_differential = strikes_per_min - strikes_absorbed
        
        takedown_accuracy = self._safe_float(snapshot.takedown_accuracy, 35.0) / 100.0
        takedown_defense = self._safe_float(snapshot.takedown_defense, 60.0) / 100.0
        takedowns_per_15 = self._safe_float(snapshot.takedown_avg_per_15min, 1.0)
        subs_per_15 = self._safe_float(snapshot.submission_avg_per_15min, 0.5)
        
        win_streak = snapshot.win_streak or 0
        loss_streak = snapshot.loss_streak or 0
        recent_form_score = self._calculate_form_score(snapshot.recent_form)
        
        days_since = snapshot.days_since_last_fight
        if days_since is not None:
            activity_score = max(0.0, 1.0 - (days_since / self.MAX_DAYS_FOR_ACTIVITY))
        else:
            activity_score = 0.5
        
        height_cm = fighter.height_cm if fighter else None
        reach_cm = fighter.reach_cm if fighter else None
        age_years = self._calculate_age(fighter, snapshot) if fighter else None
        
        return FighterFeatures(
            fighter_id=str(snapshot.fighter_id),
            fighter_name=fighter.full_name if fighter else "Unknown",
            win_rate=win_rate,
            finish_rate=finish_rate,
            ko_rate=ko_rate,
            submission_rate=submission_rate,
            total_fights=total_fights,
            experience_score=experience_score,
            striking_accuracy=striking_accuracy,
            striking_defense=striking_defense,
            strikes_per_min=strikes_per_min,
            strikes_absorbed_per_min=strikes_absorbed,
            strike_differential=strike_differential,
            takedown_accuracy=takedown_accuracy,
            takedown_defense=takedown_defense,
            takedowns_per_15min=takedowns_per_15,
            submissions_per_15min=subs_per_15,
            win_streak=win_streak,
            loss_streak=loss_streak,
            recent_form_score=recent_form_score,
            days_since_fight=days_since,
            activity_score=activity_score,
            height_cm=height_cm,
            reach_cm=reach_cm,
            age_years=age_years,
            raw_data={"record": snapshot.record, "total_fights": total_fights},
        )
    
    def extract_from_fighter(
        self,
        fighter: Fighter,
        wins: int = 0,
        losses: int = 0,
    ) -> FighterFeatures:
        """Extract basic features from a fighter without snapshot."""
        total_fights = wins + losses
        win_rate = wins / total_fights if total_fights > 0 else 0.5
        
        return FighterFeatures(
            fighter_id=str(fighter.id),
            fighter_name=fighter.full_name,
            win_rate=win_rate,
            total_fights=total_fights,
            experience_score=min(1.0, total_fights / self.MAX_FIGHTS_FOR_EXPERIENCE),
            height_cm=fighter.height_cm,
            reach_cm=fighter.reach_cm,
        )
    
    def _safe_float(self, value: Any, default: float) -> float:
        """Safely convert to float with default."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _calculate_form_score(self, recent_form: str | None) -> float:
        """Calculate form score from recent results string."""
        if not recent_form:
            return 0.0
        
        score = 0.0
        weights = [0.35, 0.25, 0.20, 0.12, 0.08]
        results = list(reversed(recent_form.upper()))
        
        for i, result in enumerate(results[:5]):
            weight = weights[i] if i < len(weights) else 0.05
            if result == 'W':
                score += weight
            elif result == 'L':
                score -= weight
        
        return score
    
    def _calculate_age(self, fighter: Fighter, snapshot: FighterSnapshot) -> float | None:
        """Calculate fighter's age at time of snapshot."""
        if not fighter.date_of_birth or not snapshot.snapshot_date:
            return None
        
        dob = fighter.date_of_birth
        fight_date = snapshot.snapshot_date
        
        age = fight_date.year - dob.year
        if (fight_date.month, fight_date.day) < (dob.month, dob.day):
            age -= 1
        
        return float(age)
