"""Unit tests for the prediction engine."""

import pytest

from app.prediction_engine.feature_extractor import FeatureExtractor, FighterFeatures
from app.prediction_engine.predictor import Prediction, RuleBasedPredictor
from app.prediction_engine.weights import PredictionWeights
from app.prediction_engine.confidence import ConfidenceScorer


class TestPredictionWeights:
    """Tests for PredictionWeights."""

    def test_default_weights(self):
        """Test default weights are reasonable."""
        weights = PredictionWeights.default()
        total = weights.total_weight()
        # Weights should sum to approximately 1.0
        assert 0.95 <= total <= 1.05

    def test_striking_focused_weights(self):
        """Test striking-focused preset."""
        weights = PredictionWeights.striking_focused()
        assert weights.strike_differential > PredictionWeights.default().strike_differential

    def test_grappling_focused_weights(self):
        """Test grappling-focused preset."""
        weights = PredictionWeights.grappling_focused()
        assert weights.takedown_defense > PredictionWeights.default().takedown_defense


class TestFighterFeatures:
    """Tests for FighterFeatures dataclass."""

    def test_default_values(self):
        """Test default feature values."""
        features = FighterFeatures(
            fighter_id="test-id",
            fighter_name="Test Fighter",
        )
        assert features.win_rate == 0.0
        assert features.total_fights == 0
        assert features.strike_differential == 0.0


class TestFeatureExtractor:
    """Tests for FeatureExtractor."""

    def test_safe_float_with_none(self):
        """Test _safe_float handles None."""
        extractor = FeatureExtractor()
        assert extractor._safe_float(None, 5.0) == 5.0

    def test_safe_float_with_value(self):
        """Test _safe_float with valid value."""
        extractor = FeatureExtractor()
        assert extractor._safe_float(3.5, 5.0) == 3.5

    def test_safe_float_with_invalid(self):
        """Test _safe_float with invalid value."""
        extractor = FeatureExtractor()
        assert extractor._safe_float("invalid", 5.0) == 5.0

    def test_calculate_form_score_all_wins(self):
        """Test form score with all wins."""
        extractor = FeatureExtractor()
        score = extractor._calculate_form_score("WWWWW")
        assert score > 0.8  # Should be high

    def test_calculate_form_score_all_losses(self):
        """Test form score with all losses."""
        extractor = FeatureExtractor()
        score = extractor._calculate_form_score("LLLLL")
        assert score < -0.8  # Should be very negative

    def test_calculate_form_score_mixed(self):
        """Test form score with mixed results."""
        extractor = FeatureExtractor()
        score = extractor._calculate_form_score("WLWLW")
        assert -0.5 < score < 0.5  # Should be moderate

    def test_calculate_form_score_empty(self):
        """Test form score with empty string."""
        extractor = FeatureExtractor()
        score = extractor._calculate_form_score("")
        assert score == 0.0

    def test_calculate_form_score_none(self):
        """Test form score with None."""
        extractor = FeatureExtractor()
        score = extractor._calculate_form_score(None)
        assert score == 0.0


class TestRuleBasedPredictor:
    """Tests for RuleBasedPredictor."""

    @pytest.fixture
    def predictor(self):
        """Create predictor instance."""
        return RuleBasedPredictor()

    @pytest.fixture
    def strong_fighter(self):
        """Create features for a strong fighter."""
        return FighterFeatures(
            fighter_id="fighter-1",
            fighter_name="Strong Fighter",
            win_rate=0.85,
            finish_rate=0.6,
            ko_rate=0.4,
            total_fights=25,
            experience_score=0.625,
            striking_accuracy=0.55,
            striking_defense=0.65,
            strikes_per_min=5.0,
            strike_differential=1.5,
            takedown_accuracy=0.5,
            takedown_defense=0.75,
            win_streak=3,
            recent_form_score=0.8,
            reach_cm=190.0,
        )

    @pytest.fixture
    def weak_fighter(self):
        """Create features for a weaker fighter."""
        return FighterFeatures(
            fighter_id="fighter-2",
            fighter_name="Weak Fighter",
            win_rate=0.45,
            finish_rate=0.3,
            ko_rate=0.2,
            total_fights=10,
            experience_score=0.25,
            striking_accuracy=0.40,
            striking_defense=0.45,
            strikes_per_min=2.5,
            strike_differential=-0.5,
            takedown_accuracy=0.3,
            takedown_defense=0.55,
            loss_streak=2,
            recent_form_score=-0.5,
            reach_cm=175.0,
        )

    def test_predict_strong_vs_weak(self, predictor, strong_fighter, weak_fighter):
        """Test prediction favors stronger fighter."""
        prediction = predictor.predict(strong_fighter, weak_fighter)

        assert prediction.predicted_winner_id == strong_fighter.fighter_id
        assert prediction.win_probability > 0.6
        assert prediction.fighter1_advantage > 0

    def test_predict_weak_vs_strong(self, predictor, strong_fighter, weak_fighter):
        """Test prediction with reversed order."""
        prediction = predictor.predict(weak_fighter, strong_fighter)

        assert prediction.predicted_winner_id == strong_fighter.fighter_id
        assert prediction.win_probability > 0.6
        assert prediction.fighter1_advantage < 0  # Negative = fighter2 favored

    def test_predict_equal_fighters(self, predictor):
        """Test prediction with evenly matched fighters."""
        fighter1 = FighterFeatures(
            fighter_id="fighter-1",
            fighter_name="Fighter One",
            win_rate=0.6,
            total_fights=15,
            experience_score=0.375,
        )
        fighter2 = FighterFeatures(
            fighter_id="fighter-2",
            fighter_name="Fighter Two",
            win_rate=0.6,
            total_fights=15,
            experience_score=0.375,
        )

        prediction = predictor.predict(fighter1, fighter2)

        # Close matchup should have probability near 50%
        assert 0.45 <= prediction.win_probability <= 0.55
        assert prediction.confidence_label in ["Low", "Medium"]

    def test_prediction_has_required_fields(self, predictor, strong_fighter, weak_fighter):
        """Test prediction contains all required fields."""
        prediction = predictor.predict(strong_fighter, weak_fighter)

        assert prediction.fighter1_id == strong_fighter.fighter_id
        assert prediction.fighter2_id == weak_fighter.fighter_id
        assert prediction.predicted_winner_name is not None
        assert 0.5 <= prediction.win_probability <= 1.0
        assert 0.0 <= prediction.confidence <= 1.0
        assert prediction.confidence_label in ["Low", "Medium", "High"]
        assert prediction.advantage_breakdown is not None

    def test_advantage_breakdown(self, predictor, strong_fighter, weak_fighter):
        """Test advantage breakdown is calculated."""
        prediction = predictor.predict(strong_fighter, weak_fighter)
        breakdown = prediction.advantage_breakdown

        # Strong fighter should have advantages in most categories
        assert breakdown.record > 0  # Better win rate
        assert breakdown.striking > 0  # Better striking
        assert breakdown.form > 0  # Better form
        assert breakdown.total > 0  # Overall advantage

    def test_warnings_for_inexperienced(self, predictor):
        """Test warnings are generated for inexperienced fighters."""
        rookie1 = FighterFeatures(
            fighter_id="rookie-1",
            fighter_name="Rookie One",
            total_fights=2,
        )
        rookie2 = FighterFeatures(
            fighter_id="rookie-2",
            fighter_name="Rookie Two",
            total_fights=1,
        )

        prediction = predictor.predict(rookie1, rookie2)

        assert len(prediction.warnings) >= 1
        assert any("limited" in w.lower() for w in prediction.warnings)


class TestConfidenceScorer:
    """Tests for ConfidenceScorer."""

    @pytest.fixture
    def scorer(self):
        """Create scorer instance."""
        return ConfidenceScorer()

    def test_high_experience_score(self, scorer):
        """Test experience assessment for veterans."""
        f1 = FighterFeatures(fighter_id="1", fighter_name="F1", total_fights=25)
        f2 = FighterFeatures(fighter_id="2", fighter_name="F2", total_fights=20)

        score = scorer._assess_experience(f1, f2)
        assert score >= 0.75

    def test_low_experience_score(self, scorer):
        """Test experience assessment for rookies."""
        f1 = FighterFeatures(fighter_id="1", fighter_name="F1", total_fights=2)
        f2 = FighterFeatures(fighter_id="2", fighter_name="F2", total_fights=1)

        score = scorer._assess_experience(f1, f2)
        assert score <= 0.2

    def test_clear_matchup_high_clarity(self, scorer):
        """Test clarity assessment for clear matchup."""
        score = scorer._assess_clarity(0.35)
        assert score >= 0.8

    def test_close_matchup_low_clarity(self, scorer):
        """Test clarity assessment for close matchup."""
        score = scorer._assess_clarity(0.02)
        assert score <= 0.3


class TestPredictionToDict:
    """Test Prediction serialization."""

    def test_to_dict(self):
        """Test prediction converts to dictionary."""
        from app.prediction_engine.predictor import AdvantageBreakdown

        prediction = Prediction(
            fight_id="test-fight-id",
            fighter1_id="f1",
            fighter2_id="f2",
            fighter1_name="Fighter One",
            fighter2_name="Fighter Two",
            predicted_winner_id="f1",
            predicted_winner_name="Fighter One",
            win_probability=0.65,
            confidence=0.7,
            confidence_label="High",
            fighter1_advantage=0.15,
            advantage_breakdown=AdvantageBreakdown(
                record=0.05,
                striking=0.04,
                grappling=0.03,
                form=0.02,
                physical=0.01,
            ),
            predicted_method="Decision",
            factors=["Better win rate", "Striking advantage"],
            warnings=[],
        )

        result = prediction.to_dict()

        assert result["fight_id"] == "test-fight-id"
        assert result["predicted_winner"]["id"] == "f1"
        assert result["predicted_winner"]["probability"] == 0.65
        assert result["confidence"]["label"] == "High"
        assert result["advantage_breakdown"]["total"] == 0.15
        assert result["predicted_method"] == "Decision"
        assert len(result["key_factors"]) == 2
