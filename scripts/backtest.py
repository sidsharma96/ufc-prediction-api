#!/usr/bin/env python
"""Backtest script for prediction accuracy validation.

This script tests the prediction engine against historical fight data
to measure accuracy and identify areas for improvement.

Usage:
    python scripts/backtest.py [--limit N] [--verbose]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Fight
from app.db.session import AsyncSessionLocal
from app.prediction_engine import FeatureExtractor, PredictionWeights, RuleBasedPredictor


async def run_backtest(limit: int = 500, verbose: bool = False) -> dict:
    """Run backtest on historical fights.

    Args:
        limit: Maximum number of fights to test
        verbose: Print details for each prediction

    Returns:
        Dictionary with accuracy statistics
    """
    print(f"Running backtest on up to {limit} fights...")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # Load completed fights with snapshots
        result = await db.execute(
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
            .limit(limit)
        )
        fights = list(result.scalars().all())

        print(f"Found {len(fights)} completed fights with results\n")

        if not fights:
            print("No fights to test. Import historical data first.")
            return {"accuracy": 0, "total": 0}

        # Initialize components
        extractor = FeatureExtractor()
        predictor = RuleBasedPredictor(PredictionWeights.default())

        # Track results
        stats = {
            "total": 0,
            "correct": 0,
            "by_confidence": {
                "High": {"correct": 0, "total": 0},
                "Medium": {"correct": 0, "total": 0},
                "Low": {"correct": 0, "total": 0},
            },
            "by_method": {
                "KO/TKO": {"correct": 0, "total": 0},
                "Submission": {"correct": 0, "total": 0},
                "Decision": {"correct": 0, "total": 0},
            },
            "errors": [],
        }

        for fight in fights:
            try:
                # Get snapshots for this fight
                f1_snapshot = None
                f2_snapshot = None
                for snap in fight.snapshots:
                    if snap.fighter_id == fight.fighter1_id:
                        f1_snapshot = snap
                    elif snap.fighter_id == fight.fighter2_id:
                        f2_snapshot = snap

                if not f1_snapshot or not f2_snapshot:
                    continue

                if not fight.fighter1 or not fight.fighter2:
                    continue

                # Extract features
                f1_features = extractor.extract_from_snapshot(
                    f1_snapshot, fight.fighter1
                )
                f2_features = extractor.extract_from_snapshot(
                    f2_snapshot, fight.fighter2
                )

                # Make prediction
                prediction = predictor.predict(
                    f1_features, f2_features, fight_id=str(fight.id)
                )

                # Check result
                stats["total"] += 1
                is_correct = prediction.predicted_winner_id == str(fight.winner_id)

                if is_correct:
                    stats["correct"] += 1

                # Track by confidence
                conf = prediction.confidence_label
                stats["by_confidence"][conf]["total"] += 1
                if is_correct:
                    stats["by_confidence"][conf]["correct"] += 1

                # Track by actual method
                method = fight.result_method or "Unknown"
                if "KO" in method.upper() or "TKO" in method.upper():
                    method_key = "KO/TKO"
                elif "SUB" in method.upper():
                    method_key = "Submission"
                elif "DEC" in method.upper():
                    method_key = "Decision"
                else:
                    method_key = None

                if method_key and method_key in stats["by_method"]:
                    stats["by_method"][method_key]["total"] += 1
                    if is_correct:
                        stats["by_method"][method_key]["correct"] += 1

                # Verbose output
                if verbose:
                    result_icon = "✓" if is_correct else "✗"
                    actual_winner = (
                        fight.fighter1.full_name
                        if fight.winner_id == fight.fighter1_id
                        else fight.fighter2.full_name
                    )
                    print(
                        f"{result_icon} {fight.fighter1.full_name} vs {fight.fighter2.full_name}"
                    )
                    print(
                        f"  Predicted: {prediction.predicted_winner_name} "
                        f"({prediction.win_probability:.1%}, {prediction.confidence_label})"
                    )
                    print(f"  Actual: {actual_winner} via {fight.result_method}")
                    print()

            except Exception as e:
                stats["errors"].append(str(e))
                continue

        # Calculate final accuracy
        accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0

        # Print summary
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"\nOverall Accuracy: {accuracy:.1%} ({stats['correct']}/{stats['total']})")

        print("\nBy Confidence Level:")
        for conf, data in stats["by_confidence"].items():
            if data["total"] > 0:
                conf_acc = data["correct"] / data["total"]
                print(f"  {conf}: {conf_acc:.1%} ({data['correct']}/{data['total']})")

        print("\nBy Result Method:")
        for method, data in stats["by_method"].items():
            if data["total"] > 0:
                method_acc = data["correct"] / data["total"]
                print(f"  {method}: {method_acc:.1%} ({data['correct']}/{data['total']})")

        if stats["errors"]:
            print(f"\nErrors encountered: {len(stats['errors'])}")

        # Target check
        print("\n" + "-" * 60)
        if accuracy >= 0.55:
            print(f"✓ Target accuracy (>55%) ACHIEVED: {accuracy:.1%}")
        else:
            print(f"✗ Target accuracy (>55%) not met: {accuracy:.1%}")

        return {
            "accuracy": accuracy,
            "total": stats["total"],
            "correct": stats["correct"],
            "by_confidence": stats["by_confidence"],
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backtest prediction accuracy on historical fights"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of fights to test (default: 500)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print details for each prediction",
    )
    args = parser.parse_args()

    asyncio.run(run_backtest(limit=args.limit, verbose=args.verbose))


if __name__ == "__main__":
    main()
