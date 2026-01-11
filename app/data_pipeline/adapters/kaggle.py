"""Kaggle UFC dataset adapter.

Parses CSV files from common Kaggle UFC datasets.
Supports the popular "UFC Fight Data" format and similar datasets.
"""

import contextlib
import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.data_pipeline.adapters.base import (
    DataSourceAdapter,
    DataSourceType,
    RawEvent,
    RawFight,
    RawFighter,
)


def parse_date(date_str: str | None) -> date | None:
    """Parse date from various formats."""
    if not date_str or date_str.strip() == "":
        return None

    date_str = date_str.strip()

    # Try common formats
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    return None


def parse_height_to_cm(height_str: str | None) -> float | None:
    """Parse height string to centimeters.

    Handles formats like: "5'11\"", "5' 11\"", "180 cm", "180"
    """
    if not height_str or height_str.strip() == "":
        return None

    height_str = height_str.strip()

    # Check for feet/inches format (5'11" or 5' 11")
    ft_in_match = re.match(r"(\d+)['\s]+(\d+)", height_str)
    if ft_in_match:
        feet = int(ft_in_match.group(1))
        inches = int(ft_in_match.group(2))
        return round((feet * 12 + inches) * 2.54, 1)

    # Check for cm format
    cm_match = re.match(r"(\d+(?:\.\d+)?)\s*(?:cm)?", height_str)
    if cm_match:
        value = float(cm_match.group(1))
        # If value is reasonable for cm, return it
        if value > 100:
            return round(value, 1)
        # Otherwise assume it's already in some unit that needs conversion
        return None

    return None


def parse_reach_to_cm(reach_str: str | None) -> float | None:
    """Parse reach string to centimeters.

    Handles formats like: "74\"", "74", "188 cm"
    """
    if not reach_str or reach_str.strip() == "":
        return None

    reach_str = reach_str.strip().replace('"', "").replace("'", "")

    # Check for cm format first
    if "cm" in reach_str.lower():
        cm_match = re.match(r"(\d+(?:\.\d+)?)", reach_str)
        if cm_match:
            return round(float(cm_match.group(1)), 1)

    # Assume inches if just a number
    try:
        inches = float(reach_str)
        if inches < 100:  # Reasonable inch value
            return round(inches * 2.54, 1)
        return round(inches, 1)  # Already in cm
    except ValueError:
        return None


def parse_weight_to_kg(weight_str: str | None) -> float | None:
    """Parse weight string to kilograms.

    Handles formats like: "170 lbs", "170", "77 kg"
    """
    if not weight_str or weight_str.strip() == "":
        return None

    weight_str = weight_str.strip().lower()

    # Extract number
    num_match = re.match(r"(\d+(?:\.\d+)?)", weight_str)
    if not num_match:
        return None

    value = float(num_match.group(1))

    # Check for kg
    if "kg" in weight_str:
        return round(value, 1)

    # Check for lbs or assume lbs for typical fight weights
    if "lb" in weight_str or value > 50:  # Assume lbs if > 50
        return round(value * 0.453592, 1)

    return round(value, 1)


def normalize_weight_class(weight_class: str | None) -> str | None:
    """Normalize weight class names."""
    if not weight_class:
        return None

    weight_class = weight_class.strip().lower()

    # Map common variations
    mappings = {
        "strawweight": "Strawweight",
        "flyweight": "Flyweight",
        "bantamweight": "Bantamweight",
        "featherweight": "Featherweight",
        "lightweight": "Lightweight",
        "welterweight": "Welterweight",
        "middleweight": "Middleweight",
        "light heavyweight": "Light Heavyweight",
        "lightheavyweight": "Light Heavyweight",
        "heavyweight": "Heavyweight",
        "women's strawweight": "Women's Strawweight",
        "women's flyweight": "Women's Flyweight",
        "women's bantamweight": "Women's Bantamweight",
        "women's featherweight": "Women's Featherweight",
        "catch weight": "Catch Weight",
        "catchweight": "Catch Weight",
        "open weight": "Open Weight",
    }

    return mappings.get(weight_class, weight_class.title())


def parse_result_method(method: str | None) -> tuple[str | None, str | None]:
    """Parse result method into category and detail.

    Returns:
        Tuple of (method_category, method_detail)
        e.g., ("KO/TKO", "Punches") or ("Submission", "Rear Naked Choke")
    """
    if not method or method.strip() == "":
        return None, None

    method = method.strip()

    # Common KO/TKO patterns
    ko_patterns = [
        r"^ko(/tko)?",
        r"^tko",
        r"knockout",
        r"punch",
        r"kick",
        r"knee",
        r"elbow",
    ]

    # Common submission patterns
    sub_patterns = [
        r"submission",
        r"choke",
        r"armbar",
        r"triangle",
        r"guillotine",
        r"kimura",
        r"americana",
        r"heel hook",
        r"ankle lock",
        r"kneebar",
    ]

    # Decision patterns
    decision_patterns = [
        r"decision",
        r"unanimous",
        r"split",
        r"majority",
    ]

    method_lower = method.lower()

    # Check KO/TKO
    for pattern in ko_patterns:
        if re.search(pattern, method_lower):
            return "KO/TKO", method

    # Check Submission
    for pattern in sub_patterns:
        if re.search(pattern, method_lower):
            return "Submission", method

    # Check Decision
    for pattern in decision_patterns:
        if re.search(pattern, method_lower):
            if "unanimous" in method_lower:
                return "Decision (Unanimous)", None
            elif "split" in method_lower:
                return "Decision (Split)", None
            elif "majority" in method_lower:
                return "Decision (Majority)", None
            return "Decision", None

    # Default: return as-is
    return method, None


class KaggleAdapter(DataSourceAdapter):
    """Adapter for Kaggle UFC CSV datasets.

    Supports common Kaggle UFC dataset formats including:
    - UFC Fight Data (per-fight rows with both fighters' stats)
    - Individual fighter CSV files
    - Event CSV files

    The adapter can handle different column naming conventions
    through column mapping configuration.
    """

    def __init__(
        self,
        data_dir: str | Path,
        fights_file: str = "ufc_fights.csv",
        fighters_file: str | None = None,
        events_file: str | None = None,
        column_mapping: dict[str, str] | None = None,
    ):
        """Initialize Kaggle adapter.

        Args:
            data_dir: Directory containing CSV files
            fights_file: Main fights CSV file name
            fighters_file: Optional separate fighters CSV
            events_file: Optional separate events CSV
            column_mapping: Optional column name mappings
        """
        self.data_dir = Path(data_dir)
        self.fights_file = fights_file
        self.fighters_file = fighters_file
        self.events_file = events_file
        self.column_mapping = column_mapping or {}

        # Default column mappings for common Kaggle datasets
        self._default_mappings = {
            # Fighter 1 (Red corner)
            "r_fighter": ["r_fighter", "red_fighter", "fighter1", "fighter_1"],
            "r_height": ["r_height", "red_height", "fighter1_height"],
            "r_reach": ["r_reach", "red_reach", "fighter1_reach"],
            "r_stance": ["r_stance", "red_stance", "fighter1_stance"],
            "r_dob": ["r_dob", "red_dob", "fighter1_dob"],
            # Fighter 2 (Blue corner)
            "b_fighter": ["b_fighter", "blue_fighter", "fighter2", "fighter_2"],
            "b_height": ["b_height", "blue_height", "fighter2_height"],
            "b_reach": ["b_reach", "blue_reach", "fighter2_reach"],
            "b_stance": ["b_stance", "blue_stance", "fighter2_stance"],
            "b_dob": ["b_dob", "blue_dob", "fighter2_dob"],
            # Fight info
            "date": ["date", "event_date", "fight_date"],
            "event": ["event", "event_name", "location"],
            "weight_class": ["weight_class", "weightclass", "division"],
            "winner": ["winner", "result", "fight_winner", "status"],
            "method": ["method", "win_by", "finish"],
            "round": ["round", "last_round", "ending_round"],
            "time": ["time", "last_round_time", "ending_time"],
            "title_bout": ["title_bout", "title_fight", "is_title"],
        }

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.KAGGLE

    def _get_column(self, row: dict[str, Any], key: str) -> Any:
        """Get column value using mapping or defaults."""
        # Check explicit mapping first
        if key in self.column_mapping:
            col_name = self.column_mapping[key]
            return row.get(col_name, "")

        # Check default mappings
        if key in self._default_mappings:
            for col_name in self._default_mappings[key]:
                if col_name in row:
                    return row.get(col_name, "")

        # Try exact match
        return row.get(key, "")

    def _parse_fighter_from_row(
        self,
        row: dict[str, Any],
        prefix: str,
    ) -> RawFighter:
        """Extract fighter data from a fight row."""
        name = str(self._get_column(row, f"{prefix}_fighter") or "")

        # Split name into first/last
        name_parts = name.strip().split(maxsplit=1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        height_str = self._get_column(row, f"{prefix}_height")
        reach_str = self._get_column(row, f"{prefix}_reach")
        dob_str = self._get_column(row, f"{prefix}_dob")

        return RawFighter(
            first_name=first_name,
            last_name=last_name,
            height_cm=parse_height_to_cm(str(height_str) if height_str else None),
            reach_cm=parse_reach_to_cm(str(reach_str) if reach_str else None),
            stance=str(self._get_column(row, f"{prefix}_stance") or "").title() or None,
            date_of_birth=parse_date(str(dob_str) if dob_str else None),
            weight_class=normalize_weight_class(str(self._get_column(row, "weight_class") or "")),
            source=DataSourceType.KAGGLE,
            raw_data={"prefix": prefix, "row": dict(row)},
        )

    def _extract_fighter_stats(
        self,
        row: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        """Extract fighter stats from a row for snapshot creation."""
        stats = {}

        # Common stat columns with prefixes
        stat_keys = [
            "sig_str_landed",
            "sig_str_attempted",
            "sig_str_acc",
            "total_str_landed",
            "total_str_attempted",
            "td_landed",
            "td_attempted",
            "td_acc",
            "sub_att",
            "rev",
            "ctrl_time",
            "head_landed",
            "body_landed",
            "leg_landed",
            "distance_landed",
            "clinch_landed",
            "ground_landed",
            "ko_wins",
            "sub_wins",
            "wins",
            "losses",
            "draws",
            "current_win_streak",
            "current_lose_streak",
            "avg_sig_str_landed",
            "avg_sig_str_absorbed",
            "sig_str_defense",
            "avg_td_landed",
            "avg_td_absorbed",
            "td_defense",
            "avg_sub_att",
        ]

        for key in stat_keys:
            col_names = [
                f"{prefix}_{key}",
                f"{prefix.upper()}_{key}",
            ]
            for col_name in col_names:
                if col_name in row and row[col_name]:
                    try:
                        value = row[col_name]
                        # Handle percentage strings
                        if isinstance(value, str) and "%" in value:
                            stats[key] = float(value.replace("%", "")) / 100
                        else:
                            stats[key] = float(value)
                    except (ValueError, TypeError):
                        pass
                    break

        return stats

    async def fetch_fighters(self) -> list[RawFighter]:
        """Fetch fighters from the dataset.

        Extracts unique fighters from fight data.
        """
        fighters_dict: dict[str, RawFighter] = {}
        fights_path = self.data_dir / self.fights_file

        if not fights_path.exists():
            return []

        with open(fights_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Extract red corner fighter
                r_fighter = self._parse_fighter_from_row(row, "r")
                key_r = f"{r_fighter.first_name} {r_fighter.last_name}".strip().lower()
                if key_r and key_r not in fighters_dict:
                    fighters_dict[key_r] = r_fighter

                # Extract blue corner fighter
                b_fighter = self._parse_fighter_from_row(row, "b")
                key_b = f"{b_fighter.first_name} {b_fighter.last_name}".strip().lower()
                if key_b and key_b not in fighters_dict:
                    fighters_dict[key_b] = b_fighter

        return list(fighters_dict.values())

    async def fetch_events(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawEvent]:
        """Fetch events from the dataset."""
        events_dict: dict[str, RawEvent] = {}
        fights_path = self.data_dir / self.fights_file

        if not fights_path.exists():
            return []

        with open(fights_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                event_name = str(self._get_column(row, "event") or "").strip()
                date_str = self._get_column(row, "date")
                event_date = parse_date(str(date_str) if date_str else None)

                if not event_name or not event_date:
                    continue

                # Apply date filters
                if start_date and event_date < start_date:
                    continue
                if end_date and event_date > end_date:
                    continue

                event_key = f"{event_name}_{event_date}"
                if event_key not in events_dict:
                    # Parse event type from name
                    event_type = None
                    name_lower = event_name.lower()
                    if "ufc" in name_lower:
                        if re.search(r"ufc\s+\d+", name_lower):
                            event_type = "numbered"
                        elif (
                            "fight night" in name_lower
                            or "on espn" in name_lower
                            or "on fox" in name_lower
                        ):
                            event_type = "fight_night"

                    events_dict[event_key] = RawEvent(
                        name=event_name,
                        event_date=event_date,
                        event_type=event_type,
                        is_completed=True,  # Kaggle data is historical
                        source=DataSourceType.KAGGLE,
                        raw_data={"sample_row": dict(row)},
                    )

        return list(events_dict.values())

    async def fetch_fights(
        self,
        event_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawFight]:
        """Fetch fights from the dataset."""
        fights: list[RawFight] = []
        fights_path = self.data_dir / self.fights_file

        if not fights_path.exists():
            return []

        with open(fights_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                row_event = str(self._get_column(row, "event") or "").strip()
                date_str = self._get_column(row, "date")
                fight_date = parse_date(str(date_str) if date_str else None)

                # Apply filters
                if event_name and row_event.lower() != event_name.lower():
                    continue
                if fight_date:
                    if start_date and fight_date < start_date:
                        continue
                    if end_date and fight_date > end_date:
                        continue

                # Get fighter names
                r_name = str(self._get_column(row, "r_fighter") or "").strip()
                b_name = str(self._get_column(row, "b_fighter") or "").strip()

                if not r_name or not b_name:
                    continue

                # Parse result
                winner = str(self._get_column(row, "winner") or "").strip()
                method_raw = str(self._get_column(row, "method") or "").strip()
                method, method_detail = parse_result_method(method_raw)

                # Determine winner name
                winner_name = None
                is_draw = False
                is_no_contest = False

                if winner:
                    winner_lower = winner.lower()
                    if winner_lower in ["draw", "d"]:
                        is_draw = True
                    elif winner_lower in ["nc", "no contest"]:
                        is_no_contest = True
                    elif winner_lower in ["red", "r", "win"] or winner.lower() == r_name.lower():
                        # "win" means red corner (fighter1) won
                        winner_name = r_name
                    elif winner_lower in ["blue", "b", "loss"] or winner.lower() == b_name.lower():
                        # "loss" means blue corner (fighter2) won
                        winner_name = b_name
                    else:
                        # Winner might be the actual name
                        winner_name = winner

                # Parse round and time
                round_str = self._get_column(row, "round")
                ending_round = None
                if round_str:
                    with contextlib.suppress(ValueError, TypeError):
                        ending_round = int(round_str)

                ending_time = str(self._get_column(row, "time") or "").strip() or None

                # Parse title bout
                title_raw = self._get_column(row, "title_bout")
                is_title = False
                if title_raw:
                    title_str = str(title_raw).lower()
                    is_title = title_str in ["true", "1", "yes", "t"]

                # Get weight class
                weight_class = (
                    normalize_weight_class(str(self._get_column(row, "weight_class") or ""))
                    or "Unknown"
                )

                # Extract fighter stats for snapshots
                r_stats = self._extract_fighter_stats(row, "r")
                b_stats = self._extract_fighter_stats(row, "b")

                fights.append(
                    RawFight(
                        fighter1_name=r_name,
                        fighter2_name=b_name,
                        event_name=row_event or None,
                        event_date=fight_date,
                        weight_class=weight_class,
                        is_title_fight=is_title,
                        winner_name=winner_name,
                        result_method=method,
                        result_method_detail=method_detail,
                        ending_round=ending_round,
                        ending_time=ending_time,
                        is_draw=is_draw,
                        is_no_contest=is_no_contest,
                        fighter1_stats=r_stats,
                        fighter2_stats=b_stats,
                        source=DataSourceType.KAGGLE,
                        raw_data=dict(row),
                    )
                )

        return fights

    async def health_check(self) -> bool:
        """Check if data files exist."""
        fights_path = self.data_dir / self.fights_file
        return fights_path.exists()
