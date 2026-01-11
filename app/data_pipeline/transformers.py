"""Data transformers for normalization, validation, and deduplication."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from app.data_pipeline.adapters.base import RawEvent, RawFight, RawFighter


def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    - Strips whitespace
    - Converts to lowercase
    - Removes accents/diacritics
    - Removes special characters except hyphens and apostrophes
    """
    if not name:
        return ""

    # Normalize unicode (remove accents)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))

    # Lowercase and strip
    name = name.lower().strip()

    # Remove special characters except hyphen, apostrophe, space
    name = re.sub(r"[^\w\s\-\']", "", name)

    # Normalize whitespace
    name = re.sub(r"\s+", " ", name)

    return name


def name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names.

    Returns a score between 0 and 1.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return 0.0

    if n1 == n2:
        return 1.0

    # Check if one is contained in the other
    if n1 in n2 or n2 in n1:
        return 0.9

    # Split into parts and check overlap
    parts1 = set(n1.split())
    parts2 = set(n2.split())

    if not parts1 or not parts2:
        return 0.0

    intersection = parts1 & parts2
    union = parts1 | parts2

    # Jaccard similarity
    jaccard = len(intersection) / len(union)

    # Bonus for matching last name (typically the last word)
    words1 = n1.split()
    words2 = n2.split()
    if words1 and words2 and words1[-1] == words2[-1]:
        jaccard = min(1.0, jaccard + 0.3)

    return jaccard


@dataclass
class ValidationError:
    """Represents a validation error."""

    field: str
    message: str
    value: str | None = None


@dataclass
class ValidationResult:
    """Result of validating a data object."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, field: str, message: str, value: str | None = None) -> None:
        """Add a validation error."""
        self.errors.append(ValidationError(field=field, message=message, value=value))
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a validation warning."""
        self.warnings.append(message)


class FighterTransformer:
    """Transformer for fighter data."""

    # Valid weight classes
    VALID_WEIGHT_CLASSES = {
        "Strawweight",
        "Flyweight",
        "Bantamweight",
        "Featherweight",
        "Lightweight",
        "Welterweight",
        "Middleweight",
        "Light Heavyweight",
        "Heavyweight",
        "Women's Strawweight",
        "Women's Flyweight",
        "Women's Bantamweight",
        "Women's Featherweight",
        "Catch Weight",
        "Open Weight",
    }

    # Valid stances
    VALID_STANCES = {"Orthodox", "Southpaw", "Switch", "Open Stance"}

    @classmethod
    def validate(cls, fighter: RawFighter) -> ValidationResult:
        """Validate fighter data."""
        result = ValidationResult(is_valid=True)

        # Required fields
        if not fighter.first_name and not fighter.last_name:
            result.add_error("name", "Fighter must have at least first or last name")

        # Height validation (reasonable range: 140-220 cm)
        if fighter.height_cm is not None:
            if fighter.height_cm < 140 or fighter.height_cm > 220:
                result.add_warning(
                    f"Unusual height: {fighter.height_cm} cm for "
                    f"{fighter.first_name} {fighter.last_name}"
                )

        # Reach validation (reasonable range: 150-220 cm)
        if fighter.reach_cm is not None:
            if fighter.reach_cm < 150 or fighter.reach_cm > 220:
                result.add_warning(
                    f"Unusual reach: {fighter.reach_cm} cm for "
                    f"{fighter.first_name} {fighter.last_name}"
                )

        # Weight class validation
        if fighter.weight_class and fighter.weight_class not in cls.VALID_WEIGHT_CLASSES:
            result.add_warning(f"Unknown weight class: {fighter.weight_class}")

        # Stance validation
        if fighter.stance and fighter.stance not in cls.VALID_STANCES:
            result.add_warning(f"Unknown stance: {fighter.stance}")

        # Date of birth validation
        if fighter.date_of_birth:
            today = date.today()
            age = (today - fighter.date_of_birth).days / 365.25
            if age < 18 or age > 60:
                result.add_warning(
                    f"Unusual age: {age:.1f} years for "
                    f"{fighter.first_name} {fighter.last_name}"
                )

        return result

    @classmethod
    def normalize(cls, fighter: RawFighter) -> RawFighter:
        """Normalize fighter data."""
        # Normalize name casing
        first_name = fighter.first_name.strip().title() if fighter.first_name else ""
        last_name = fighter.last_name.strip().title() if fighter.last_name else ""

        # Handle special cases in names (Mc, O', etc.)
        for prefix in ["Mc", "O'", "De"]:
            if last_name.lower().startswith(prefix.lower()):
                last_name = prefix + last_name[len(prefix) :].title()

        # Normalize nickname
        nickname = fighter.nickname.strip() if fighter.nickname else None
        if nickname:
            # Remove quotes if present
            nickname = nickname.strip("\"'")

        # Normalize stance
        stance = fighter.stance
        if stance:
            stance = stance.strip().title()
            if stance not in cls.VALID_STANCES:
                # Try to map common variations
                stance_map = {
                    "Ortho": "Orthodox",
                    "South": "Southpaw",
                    "Southpaw": "Southpaw",
                    "Orthodox": "Orthodox",
                }
                for key, value in stance_map.items():
                    if key.lower() in stance.lower():
                        stance = value
                        break

        return RawFighter(
            first_name=first_name,
            last_name=last_name,
            nickname=nickname,
            date_of_birth=fighter.date_of_birth,
            nationality=fighter.nationality.strip().title() if fighter.nationality else None,
            hometown=fighter.hometown.strip() if fighter.hometown else None,
            height_cm=round(fighter.height_cm, 1) if fighter.height_cm else None,
            weight_kg=round(fighter.weight_kg, 1) if fighter.weight_kg else None,
            reach_cm=round(fighter.reach_cm, 1) if fighter.reach_cm else None,
            leg_reach_cm=round(fighter.leg_reach_cm, 1) if fighter.leg_reach_cm else None,
            weight_class=fighter.weight_class,
            stance=stance,
            is_active=fighter.is_active,
            ufc_id=fighter.ufc_id,
            espn_id=fighter.espn_id,
            wins=fighter.wins,
            losses=fighter.losses,
            draws=fighter.draws,
            no_contests=fighter.no_contests,
            ko_wins=fighter.ko_wins,
            submission_wins=fighter.submission_wins,
            decision_wins=fighter.decision_wins,
            source=fighter.source,
            source_url=fighter.source_url,
            raw_data=fighter.raw_data,
        )


class EventTransformer:
    """Transformer for event data."""

    @classmethod
    def validate(cls, event: RawEvent) -> ValidationResult:
        """Validate event data."""
        result = ValidationResult(is_valid=True)

        # Required fields
        if not event.name:
            result.add_error("name", "Event must have a name")

        if not event.event_date:
            result.add_error("event_date", "Event must have a date")

        # Date validation
        if event.event_date:
            today = date.today()
            if event.event_date > today and event.is_completed:
                result.add_error(
                    "is_completed",
                    "Future event cannot be marked as completed",
                    str(event.event_date),
                )

        return result

    @classmethod
    def normalize(cls, event: RawEvent) -> RawEvent:
        """Normalize event data."""
        # Normalize name
        name = event.name.strip() if event.name else ""

        # Normalize location fields
        venue = event.venue.strip() if event.venue else None
        city = event.city.strip().title() if event.city else None
        state = event.state.strip() if event.state else None
        country = event.country.strip().title() if event.country else None

        # Normalize country names
        country_map = {
            "Usa": "USA",
            "Us": "USA",
            "United States": "USA",
            "Uk": "UK",
            "United Kingdom": "UK",
            "Uae": "UAE",
        }
        if country and country in country_map:
            country = country_map[country]

        return RawEvent(
            name=name,
            event_date=event.event_date,
            venue=venue,
            city=city,
            state=state,
            country=country,
            event_type=event.event_type,
            is_completed=event.is_completed,
            ufc_id=event.ufc_id,
            espn_id=event.espn_id,
            source=event.source,
            source_url=event.source_url,
            raw_data=event.raw_data,
        )


class FightTransformer:
    """Transformer for fight data."""

    # Valid result methods
    VALID_METHODS = {
        "KO/TKO",
        "Submission",
        "Decision (Unanimous)",
        "Decision (Split)",
        "Decision (Majority)",
        "Decision",
        "DQ",
        "Overturned",
        "Could Not Continue",
        "Doctor Stoppage",
    }

    @classmethod
    def validate(cls, fight: RawFight) -> ValidationResult:
        """Validate fight data."""
        result = ValidationResult(is_valid=True)

        # Required fields
        if not fight.fighter1_name:
            result.add_error("fighter1_name", "Fight must have fighter 1")

        if not fight.fighter2_name:
            result.add_error("fighter2_name", "Fight must have fighter 2")

        if not fight.weight_class:
            result.add_error("weight_class", "Fight must have weight class")

        # Check fighters are different
        if fight.fighter1_name and fight.fighter2_name:
            if normalize_name(fight.fighter1_name) == normalize_name(fight.fighter2_name):
                result.add_error("fighters", "Fighter 1 and Fighter 2 cannot be the same")

        # Validate round
        if fight.ending_round is not None:
            if fight.ending_round < 1 or fight.ending_round > 5:
                result.add_warning(f"Unusual round number: {fight.ending_round}")

        # Validate scheduled rounds
        if fight.scheduled_rounds not in [3, 5]:
            result.add_warning(f"Unusual scheduled rounds: {fight.scheduled_rounds}")

        return result

    @classmethod
    def normalize(cls, fight: RawFight) -> RawFight:
        """Normalize fight data."""
        # Normalize fighter names
        fighter1_name = fight.fighter1_name.strip() if fight.fighter1_name else ""
        fighter2_name = fight.fighter2_name.strip() if fight.fighter2_name else ""

        # Normalize winner name
        winner_name = fight.winner_name.strip() if fight.winner_name else None

        # Normalize result method
        result_method = fight.result_method
        if result_method:
            result_method = result_method.strip()
            # Map common variations
            method_map = {
                "TKO": "KO/TKO",
                "KO": "KO/TKO",
                "SUB": "Submission",
                "DEC": "Decision",
                "UD": "Decision (Unanimous)",
                "SD": "Decision (Split)",
                "MD": "Decision (Majority)",
            }
            for key, value in method_map.items():
                if result_method.upper() == key:
                    result_method = value
                    break

        # Normalize ending time format (should be M:SS)
        ending_time = fight.ending_time
        if ending_time:
            ending_time = ending_time.strip()
            # Ensure format is M:SS
            time_match = re.match(r"(\d+):(\d{1,2})", ending_time)
            if time_match:
                minutes = int(time_match.group(1))
                seconds = int(time_match.group(2))
                ending_time = f"{minutes}:{seconds:02d}"

        return RawFight(
            fighter1_name=fighter1_name,
            fighter2_name=fighter2_name,
            event_name=fight.event_name.strip() if fight.event_name else None,
            event_date=fight.event_date,
            weight_class=fight.weight_class,
            is_title_fight=fight.is_title_fight,
            is_main_event=fight.is_main_event,
            scheduled_rounds=fight.scheduled_rounds,
            fight_order=fight.fight_order,
            winner_name=winner_name,
            result_method=result_method,
            result_method_detail=fight.result_method_detail,
            ending_round=fight.ending_round,
            ending_time=ending_time,
            is_no_contest=fight.is_no_contest,
            is_draw=fight.is_draw,
            fighter1_stats=fight.fighter1_stats,
            fighter2_stats=fight.fighter2_stats,
            source=fight.source,
            raw_data=fight.raw_data,
        )


class Deduplicator:
    """Handles deduplication of fighters and events."""

    def __init__(self, similarity_threshold: float = 0.85):
        """Initialize deduplicator.

        Args:
            similarity_threshold: Minimum similarity score to consider a match
        """
        self.similarity_threshold = similarity_threshold

    def find_duplicate_fighters(
        self,
        fighters: list[RawFighter],
    ) -> list[tuple[int, int, float]]:
        """Find potential duplicate fighters.

        Returns:
            List of tuples (index1, index2, similarity_score)
        """
        duplicates = []

        for i, f1 in enumerate(fighters):
            name1 = f"{f1.first_name} {f1.last_name}"
            for j, f2 in enumerate(fighters[i + 1 :], start=i + 1):
                name2 = f"{f2.first_name} {f2.last_name}"
                similarity = name_similarity(name1, name2)

                if similarity >= self.similarity_threshold:
                    duplicates.append((i, j, similarity))

        return duplicates

    def merge_fighters(
        self,
        primary: RawFighter,
        secondary: RawFighter,
    ) -> RawFighter:
        """Merge two fighter records, preferring primary's data.

        Args:
            primary: Primary fighter record (preferred)
            secondary: Secondary fighter record (fallback)

        Returns:
            Merged fighter record
        """
        return RawFighter(
            first_name=primary.first_name or secondary.first_name,
            last_name=primary.last_name or secondary.last_name,
            nickname=primary.nickname or secondary.nickname,
            date_of_birth=primary.date_of_birth or secondary.date_of_birth,
            nationality=primary.nationality or secondary.nationality,
            hometown=primary.hometown or secondary.hometown,
            height_cm=primary.height_cm or secondary.height_cm,
            weight_kg=primary.weight_kg or secondary.weight_kg,
            reach_cm=primary.reach_cm or secondary.reach_cm,
            leg_reach_cm=primary.leg_reach_cm or secondary.leg_reach_cm,
            weight_class=primary.weight_class or secondary.weight_class,
            stance=primary.stance or secondary.stance,
            is_active=primary.is_active,
            ufc_id=primary.ufc_id or secondary.ufc_id,
            espn_id=primary.espn_id or secondary.espn_id,
            wins=max(primary.wins, secondary.wins),
            losses=max(primary.losses, secondary.losses),
            draws=max(primary.draws, secondary.draws),
            no_contests=max(primary.no_contests, secondary.no_contests),
            ko_wins=max(primary.ko_wins, secondary.ko_wins),
            submission_wins=max(primary.submission_wins, secondary.submission_wins),
            decision_wins=max(primary.decision_wins, secondary.decision_wins),
            source=primary.source,
            source_url=primary.source_url or secondary.source_url,
            raw_data={**secondary.raw_data, **primary.raw_data},
        )

    def deduplicate_fighters(
        self,
        fighters: list[RawFighter],
    ) -> list[RawFighter]:
        """Remove duplicate fighters from list.

        Args:
            fighters: List of fighters to deduplicate

        Returns:
            Deduplicated list of fighters
        """
        if not fighters:
            return []

        # Find duplicates
        duplicates = self.find_duplicate_fighters(fighters)

        # Build set of indices to remove
        to_remove: set[int] = set()
        merged_indices: dict[int, RawFighter] = {}

        for i, j, _similarity in duplicates:
            if i in to_remove or j in to_remove:
                continue

            # Merge j into i
            primary = merged_indices.get(i, fighters[i])
            secondary = fighters[j]
            merged_indices[i] = self.merge_fighters(primary, secondary)
            to_remove.add(j)

        # Build result
        result = []
        for i, fighter in enumerate(fighters):
            if i in to_remove:
                continue
            if i in merged_indices:
                result.append(merged_indices[i])
            else:
                result.append(fighter)

        return result
