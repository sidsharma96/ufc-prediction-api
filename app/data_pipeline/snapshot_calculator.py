"""Snapshot calculator for point-in-time fighter statistics.

This module calculates fighter statistics at the time of each fight,
which is critical for avoiding data leakage in predictions.

Data leakage occurs when future information (stats from fights that
haven't happened yet) is used to make predictions. By calculating
point-in-time snapshots, we ensure predictions only use data that
was available at the time of the fight.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Event, Fight, Fighter, FighterSnapshot


@dataclass
class FightRecord:
    """Record of a single fight for stat calculation."""

    fight_id: uuid.UUID
    event_date: date
    opponent_id: uuid.UUID
    weight_class: str
    is_title_fight: bool
    is_main_event: bool

    # Result
    won: bool
    is_draw: bool
    is_no_contest: bool
    result_method: str | None
    ending_round: int | None

    # Stats from the fight (if available)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class CalculatedStats:
    """Calculated statistics for a fighter at a point in time."""

    # Record
    wins: int = 0
    losses: int = 0
    draws: int = 0
    no_contests: int = 0

    # Win methods
    ko_wins: int = 0
    submission_wins: int = 0
    decision_wins: int = 0

    # Loss methods
    ko_losses: int = 0
    submission_losses: int = 0
    decision_losses: int = 0

    # Streaks
    current_win_streak: int = 0
    current_lose_streak: int = 0
    longest_win_streak: int = 0

    # Finish rates (as percentages)
    finish_rate: float | None = None
    ko_rate: float | None = None
    submission_rate: float | None = None

    # Title fights
    title_fight_wins: int = 0
    title_fight_losses: int = 0

    # Performance stats (averages from available fight data)
    avg_fight_time_seconds: float | None = None
    fights_in_weight_class: int = 0

    # Recent form (last 5 fights)
    recent_wins: int = 0
    recent_losses: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "no_contests": self.no_contests,
            "ko_wins": self.ko_wins,
            "submission_wins": self.submission_wins,
            "decision_wins": self.decision_wins,
            "ko_losses": self.ko_losses,
            "submission_losses": self.submission_losses,
            "decision_losses": self.decision_losses,
            "current_win_streak": self.current_win_streak,
            "current_lose_streak": self.current_lose_streak,
            "longest_win_streak": self.longest_win_streak,
            "finish_rate": self.finish_rate,
            "ko_rate": self.ko_rate,
            "submission_rate": self.submission_rate,
            "title_fight_wins": self.title_fight_wins,
            "title_fight_losses": self.title_fight_losses,
            "avg_fight_time_seconds": self.avg_fight_time_seconds,
            "fights_in_weight_class": self.fights_in_weight_class,
            "recent_wins": self.recent_wins,
            "recent_losses": self.recent_losses,
        }


def parse_time_to_seconds(time_str: str | None, round_num: int | None) -> int | None:
    """Convert fight time to total seconds.

    Args:
        time_str: Time in round (e.g., "4:32")
        round_num: Round number

    Returns:
        Total fight time in seconds, or None if can't parse
    """
    if not time_str or not round_num:
        return None

    try:
        parts = time_str.split(":")
        if len(parts) != 2:
            return None
        minutes = int(parts[0])
        seconds = int(parts[1])

        # Each round is 5 minutes
        completed_rounds = round_num - 1
        return (completed_rounds * 5 * 60) + (minutes * 60) + seconds
    except (ValueError, IndexError):
        return None


def is_ko_method(method: str | None) -> bool:
    """Check if method is KO/TKO."""
    if not method:
        return False
    method_lower = method.lower()
    return "ko" in method_lower or "tko" in method_lower


def is_submission_method(method: str | None) -> bool:
    """Check if method is submission."""
    if not method:
        return False
    return "sub" in method.lower()


def is_decision_method(method: str | None) -> bool:
    """Check if method is decision."""
    if not method:
        return False
    return "decision" in method.lower() or "dec" in method.lower()


class SnapshotCalculator:
    """Calculates point-in-time fighter statistics.

    This calculator processes fight history chronologically to compute
    statistics that were accurate at the time of each fight, ensuring
    no data leakage in predictions.
    """

    def __init__(self, db: AsyncSession):
        """Initialize calculator.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_fighter_history(
        self,
        fighter_id: uuid.UUID,
        before_date: date | None = None,
    ) -> list[FightRecord]:
        """Get fighter's fight history up to a specific date.

        Args:
            fighter_id: Fighter UUID
            before_date: Only include fights before this date

        Returns:
            List of fight records ordered by date
        """
        # Build query for fights involving this fighter
        from sqlalchemy import or_

        query = (
            select(Fight)
            .join(Event)
            .where(
                or_(
                    Fight.fighter1_id == fighter_id,
                    Fight.fighter2_id == fighter_id,
                ),
                Fight.status == "completed",
            )
            .options(selectinload(Fight.event))
            .order_by(Event.date.asc())
        )

        if before_date:
            query = query.where(Event.date < before_date)

        result = await self.db.execute(query)
        fights = result.scalars().all()

        # Convert to FightRecords
        records = []
        for fight in fights:
            is_fighter1 = fight.fighter1_id == fighter_id
            opponent_id = fight.fighter2_id if is_fighter1 else fight.fighter1_id

            # Determine if won
            won = False
            if fight.winner_id == fighter_id:
                won = True

            records.append(
                FightRecord(
                    fight_id=fight.id,
                    event_date=fight.event.date,
                    opponent_id=opponent_id,
                    weight_class=fight.weight_class,
                    is_title_fight=fight.is_title_fight,
                    is_main_event=fight.is_main_event,
                    won=won,
                    is_draw=fight.is_draw,
                    is_no_contest=fight.is_no_contest,
                    result_method=fight.result_method,
                    ending_round=fight.ending_round,
                )
            )

        return records

    def calculate_stats(
        self,
        fight_history: list[FightRecord],
        weight_class: str | None = None,
    ) -> CalculatedStats:
        """Calculate statistics from fight history.

        Args:
            fight_history: List of fight records in chronological order
            weight_class: Current weight class for weight-class-specific stats

        Returns:
            Calculated statistics
        """
        stats = CalculatedStats()

        if not fight_history:
            return stats

        current_streak = 0
        streak_is_wins = True
        longest_win_streak = 0
        fight_times: list[int] = []

        for fight in fight_history:
            # Skip no contests for most stats
            if fight.is_no_contest:
                stats.no_contests += 1
                continue

            # Handle draws
            if fight.is_draw:
                stats.draws += 1
                current_streak = 0
                continue

            # Count weight class specific fights
            if weight_class and fight.weight_class == weight_class:
                stats.fights_in_weight_class += 1

            # Track fight time
            if fight.result_method and fight.ending_round:
                ending_time = getattr(fight, "ending_time", None)
                actual_time = parse_time_to_seconds(ending_time, fight.ending_round)
                if actual_time:
                    fight_times.append(actual_time)

            if fight.won:
                stats.wins += 1

                # Win method
                if is_ko_method(fight.result_method):
                    stats.ko_wins += 1
                elif is_submission_method(fight.result_method):
                    stats.submission_wins += 1
                elif is_decision_method(fight.result_method):
                    stats.decision_wins += 1

                # Title fights
                if fight.is_title_fight:
                    stats.title_fight_wins += 1

                # Streak tracking
                if streak_is_wins:
                    current_streak += 1
                    longest_win_streak = max(longest_win_streak, current_streak)
                else:
                    current_streak = 1
                    streak_is_wins = True

            else:
                stats.losses += 1

                # Loss method
                if is_ko_method(fight.result_method):
                    stats.ko_losses += 1
                elif is_submission_method(fight.result_method):
                    stats.submission_losses += 1
                elif is_decision_method(fight.result_method):
                    stats.decision_losses += 1

                # Title fights
                if fight.is_title_fight:
                    stats.title_fight_losses += 1

                # Streak tracking
                if not streak_is_wins:
                    current_streak += 1
                else:
                    current_streak = 1
                    streak_is_wins = False

        # Set final streak values
        if streak_is_wins:
            stats.current_win_streak = current_streak
            stats.current_lose_streak = 0
        else:
            stats.current_win_streak = 0
            stats.current_lose_streak = current_streak

        stats.longest_win_streak = longest_win_streak

        # Calculate rates
        total_fights = stats.wins + stats.losses
        if total_fights > 0:
            finishes = stats.ko_wins + stats.submission_wins
            stats.finish_rate = round((finishes / stats.wins * 100) if stats.wins > 0 else 0, 1)
            stats.ko_rate = round((stats.ko_wins / stats.wins * 100) if stats.wins > 0 else 0, 1)
            stats.submission_rate = round(
                (stats.submission_wins / stats.wins * 100) if stats.wins > 0 else 0, 1
            )

        # Average fight time
        if fight_times:
            stats.avg_fight_time_seconds = sum(fight_times) / len(fight_times)

        # Recent form (last 5 fights)
        recent_fights = fight_history[-5:] if len(fight_history) >= 5 else fight_history
        for fight in recent_fights:
            if fight.is_no_contest or fight.is_draw:
                continue
            if fight.won:
                stats.recent_wins += 1
            else:
                stats.recent_losses += 1

        return stats

    async def create_snapshot(
        self,
        fighter: Fighter,
        fight: Fight,
    ) -> FighterSnapshot:
        """Create a snapshot for a fighter before a specific fight.

        Args:
            fighter: Fighter model
            fight: Fight model (the upcoming/current fight)

        Returns:
            Created FighterSnapshot
        """
        # Get event date
        event = fight.event
        if not event:
            result = await self.db.execute(
                select(Event).where(Event.id == fight.event_id)
            )
            event = result.scalar_one()

        # Get fight history before this fight
        history = await self.get_fighter_history(
            fighter_id=fighter.id,
            before_date=event.date,
        )

        # Calculate stats
        stats = self.calculate_stats(history, weight_class=fight.weight_class)

        # Create snapshot
        snapshot = FighterSnapshot(
            fighter_id=fighter.id,
            fight_id=fight.id,
            snapshot_date=event.date,
            # Record at time of fight
            wins=stats.wins,
            losses=stats.losses,
            draws=stats.draws,
            no_contests=stats.no_contests,
            # Calculated stats
            finish_rate=stats.finish_rate,
            ko_rate=stats.ko_rate,
            submission_rate=stats.submission_rate,
            win_streak=stats.current_win_streak,
            loss_streak=stats.current_lose_streak,
        )

        self.db.add(snapshot)
        return snapshot

    async def calculate_all_snapshots(
        self,
        limit: int | None = None,
    ) -> dict[str, int]:
        """Calculate snapshots for all historical fights.

        This should be run after importing historical data to
        populate point-in-time statistics for all fights.

        Args:
            limit: Optional limit on number of fights to process

        Returns:
            Statistics about snapshots created
        """
        stats = {
            "fights_processed": 0,
            "snapshots_created": 0,
            "errors": 0,
        }

        # Get all completed fights ordered by date
        query = (
            select(Fight)
            .join(Event)
            .where(Fight.status == "completed")
            .options(
                selectinload(Fight.fighter1),
                selectinload(Fight.fighter2),
                selectinload(Fight.event),
                selectinload(Fight.snapshots),
            )
            .order_by(Event.date.asc())
        )

        if limit:
            query = query.limit(limit)

        result = await self.db.execute(query)
        fights = result.scalars().all()

        for fight in fights:
            stats["fights_processed"] += 1

            try:
                # Check if snapshots already exist
                existing_fighter_ids = {s.fighter_id for s in fight.snapshots}

                # Create snapshot for fighter 1 if needed
                if fight.fighter1_id not in existing_fighter_ids:
                    await self.create_snapshot(fight.fighter1, fight)
                    stats["snapshots_created"] += 1

                # Create snapshot for fighter 2 if needed
                if fight.fighter2_id not in existing_fighter_ids:
                    await self.create_snapshot(fight.fighter2, fight)
                    stats["snapshots_created"] += 1

            except Exception as e:
                stats["errors"] += 1
                print(f"Error creating snapshot for fight {fight.id}: {e}")

        # Commit all snapshots
        await self.db.commit()

        return stats
