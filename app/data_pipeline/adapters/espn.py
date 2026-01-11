"""ESPN API adapter for UFC data.

Uses ESPN's unofficial API to fetch upcoming events and fight cards.
Note: This is an unofficial API and may change without notice.
"""

import re
from datetime import date, datetime
from typing import Any

import httpx

from app.data_pipeline.adapters.base import (
    DataSourceAdapter,
    DataSourceType,
    RawEvent,
    RawFight,
    RawFighter,
)


def parse_espn_date(date_str: str) -> date | None:
    """Parse ESPN date format to date object."""
    if not date_str:
        return None

    try:
        # ESPN typically uses ISO format
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.date()
    except ValueError:
        pass

    # Try other formats
    formats = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:19], fmt).date()
        except ValueError:
            continue

    return None


def extract_fighter_name(name: str) -> tuple[str, str]:
    """Extract first and last name from full name.

    Args:
        name: Full fighter name

    Returns:
        Tuple of (first_name, last_name)
    """
    if not name:
        return "", ""

    parts = name.strip().split(maxsplit=1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    return first_name, last_name


def normalize_weight_class(weight_class: str | None) -> str | None:
    """Normalize ESPN weight class to standard format."""
    if not weight_class:
        return None

    weight_class = weight_class.strip().lower()

    mappings = {
        "strawweight": "Strawweight",
        "flyweight": "Flyweight",
        "bantamweight": "Bantamweight",
        "featherweight": "Featherweight",
        "lightweight": "Lightweight",
        "welterweight": "Welterweight",
        "middleweight": "Middleweight",
        "light heavyweight": "Light Heavyweight",
        "heavyweight": "Heavyweight",
        "women's strawweight": "Women's Strawweight",
        "women's flyweight": "Women's Flyweight",
        "women's bantamweight": "Women's Bantamweight",
        "women's featherweight": "Women's Featherweight",
    }

    return mappings.get(weight_class, weight_class.title())


class ESPNAdapter(DataSourceAdapter):
    """Adapter for ESPN's unofficial UFC API.

    ESPN provides event and fight data through their website API.
    This adapter fetches upcoming events and their fight cards.

    Note: This is an unofficial API and endpoints may change.
    """

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc"

    def __init__(
        self,
        timeout: float = 30.0,
        cache_ttl: int = 300,  # 5 minutes
    ):
        """Initialize ESPN adapter.

        Args:
            timeout: HTTP request timeout in seconds
            cache_ttl: Cache time-to-live in seconds
        """
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": "UFC-Prediction-API/1.0",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.ESPN

    async def _fetch_json(self, endpoint: str) -> dict[str, Any] | None:
        """Fetch JSON from ESPN API.

        Args:
            endpoint: API endpoint (appended to BASE_URL)

        Returns:
            JSON response as dict, or None on error
        """
        client = await self._get_client()
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            print(f"ESPN API error: {e}")
            return None

    async def fetch_fighters(self) -> list[RawFighter]:
        """Fetch fighters from ESPN.

        ESPN doesn't have a direct fighters endpoint,
        so we extract fighters from events/fights.

        Returns:
            List of fighters extracted from events
        """
        fighters: dict[str, RawFighter] = {}

        # Get fighters from upcoming events
        events = await self.fetch_upcoming_events()
        for event in events:
            # Fetch fight card for each event
            if event.espn_id:
                fights = await self._fetch_event_fights(event.espn_id)
                for fight in fights:
                    # Add fighter 1
                    first, last = extract_fighter_name(fight.fighter1_name)
                    key = f"{first} {last}".lower().strip()
                    if key and key not in fighters:
                        fighters[key] = RawFighter(
                            first_name=first,
                            last_name=last,
                            weight_class=fight.weight_class,
                            source=DataSourceType.ESPN,
                        )

                    # Add fighter 2
                    first, last = extract_fighter_name(fight.fighter2_name)
                    key = f"{first} {last}".lower().strip()
                    if key and key not in fighters:
                        fighters[key] = RawFighter(
                            first_name=first,
                            last_name=last,
                            weight_class=fight.weight_class,
                            source=DataSourceType.ESPN,
                        )

        return list(fighters.values())

    async def fetch_events(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawEvent]:
        """Fetch events from ESPN.

        ESPN primarily provides upcoming events through their scoreboard.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of events
        """
        # ESPN scoreboard provides current/upcoming events
        data = await self._fetch_json("/scoreboard")
        if not data:
            return []

        events: list[RawEvent] = []
        espn_events = data.get("events", [])

        for event_data in espn_events:
            event = self._parse_event(event_data)
            if not event:
                continue

            # Apply date filters
            if start_date and event.event_date < start_date:
                continue
            if end_date and event.event_date > end_date:
                continue

            events.append(event)

        return events

    async def fetch_upcoming_events(self) -> list[RawEvent]:
        """Fetch upcoming UFC events.

        Returns:
            List of upcoming events
        """
        data = await self._fetch_json("/scoreboard")
        if not data:
            return []

        events: list[RawEvent] = []
        espn_events = data.get("events", [])

        today = date.today()
        for event_data in espn_events:
            event = self._parse_event(event_data)
            if event and event.event_date >= today:
                events.append(event)

        return events

    def _parse_event(self, event_data: dict[str, Any]) -> RawEvent | None:
        """Parse ESPN event data to RawEvent.

        Args:
            event_data: Raw event data from ESPN API

        Returns:
            RawEvent or None if parsing fails
        """
        try:
            event_id = str(event_data.get("id", ""))
            name = event_data.get("name", "")
            date_str = event_data.get("date", "")

            event_date = parse_espn_date(date_str)
            if not name or not event_date:
                return None

            # Parse venue info
            venue = None
            city = None
            state = None
            country = None

            competitions = event_data.get("competitions", [])
            if competitions:
                venue_data = competitions[0].get("venue", {})
                address = venue_data.get("address", {})

                venue = venue_data.get("fullName")
                city = address.get("city")
                state = address.get("state")
                country = address.get("country")

            # Determine event type
            event_type = None
            name_lower = name.lower()
            if re.search(r"ufc\s+\d+", name_lower):
                event_type = "numbered"
            elif "fight night" in name_lower:
                event_type = "fight_night"

            # Check completion status
            status = event_data.get("status", {})
            is_completed = status.get("type", {}).get("completed", False)

            return RawEvent(
                name=name,
                event_date=event_date,
                venue=venue,
                city=city,
                state=state,
                country=country,
                event_type=event_type,
                is_completed=is_completed,
                espn_id=event_id,
                source=DataSourceType.ESPN,
                raw_data=event_data,
            )

        except (KeyError, TypeError) as e:
            print(f"Error parsing ESPN event: {e}")
            return None

    async def fetch_fights(
        self,
        event_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawFight]:
        """Fetch fights from ESPN.

        Args:
            event_name: Optional event name filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of fights
        """
        all_fights: list[RawFight] = []

        # Get events first
        events = await self.fetch_events(start_date, end_date)

        for event in events:
            if event_name and event.name.lower() != event_name.lower():
                continue

            if event.espn_id:
                fights = await self._fetch_event_fights(event.espn_id)
                # Attach event info to fights
                for fight in fights:
                    fight.event_name = event.name
                    fight.event_date = event.event_date
                all_fights.extend(fights)

        return all_fights

    async def _fetch_event_fights(self, event_id: str) -> list[RawFight]:
        """Fetch fights for a specific event.

        Args:
            event_id: ESPN event ID

        Returns:
            List of fights
        """
        data = await self._fetch_json(f"/scoreboard/{event_id}")
        if not data:
            return []

        fights: list[RawFight] = []
        event_data = data.get("events", [{}])[0] if data.get("events") else {}
        competitions = event_data.get("competitions", [])

        for i, comp in enumerate(competitions):
            fight = self._parse_fight(comp, fight_order=len(competitions) - i)
            if fight:
                fights.append(fight)

        return fights

    def _parse_fight(
        self,
        comp_data: dict[str, Any],
        fight_order: int = 0,
    ) -> RawFight | None:
        """Parse ESPN competition data to RawFight.

        Args:
            comp_data: Raw competition data from ESPN API
            fight_order: Order on the card

        Returns:
            RawFight or None if parsing fails
        """
        try:
            competitors = comp_data.get("competitors", [])
            if len(competitors) < 2:
                return None

            # Fighter data
            fighter1_data = competitors[0]
            fighter2_data = competitors[1]

            fighter1_name = fighter1_data.get("athlete", {}).get("displayName", "")
            fighter2_name = fighter2_data.get("athlete", {}).get("displayName", "")

            if not fighter1_name or not fighter2_name:
                return None

            # Weight class
            weight_class = normalize_weight_class(
                comp_data.get("type", {}).get("text", "")
            ) or "Unknown"

            # Is title fight
            is_title = "title" in comp_data.get("type", {}).get("text", "").lower()

            # Is main event (first fight in reversed order)
            is_main = fight_order == 1

            # Scheduled rounds
            scheduled_rounds = 3
            if is_title or is_main:
                scheduled_rounds = 5

            # Result (if completed)
            winner_name = None
            result_method = None
            ending_round = None
            ending_time = None
            is_draw = False
            is_no_contest = False

            status = comp_data.get("status", {})
            is_completed = status.get("type", {}).get("completed", False)

            if is_completed:
                # Check for winner
                for comp in competitors:
                    if comp.get("winner", False):
                        winner_name = comp.get("athlete", {}).get("displayName", "")
                        break

                # Result details
                result_text = status.get("type", {}).get("detail", "")
                if result_text:
                    # Parse method and round from detail
                    if "draw" in result_text.lower():
                        is_draw = True
                    elif "no contest" in result_text.lower():
                        is_no_contest = True
                    else:
                        result_method = result_text

            return RawFight(
                fighter1_name=fighter1_name,
                fighter2_name=fighter2_name,
                weight_class=weight_class,
                is_title_fight=is_title,
                is_main_event=is_main,
                scheduled_rounds=scheduled_rounds,
                fight_order=fight_order,
                winner_name=winner_name,
                result_method=result_method,
                ending_round=ending_round,
                ending_time=ending_time,
                is_draw=is_draw,
                is_no_contest=is_no_contest,
                source=DataSourceType.ESPN,
                raw_data=comp_data,
            )

        except (KeyError, TypeError) as e:
            print(f"Error parsing ESPN fight: {e}")
            return None

    async def health_check(self) -> bool:
        """Check if ESPN API is accessible."""
        data = await self._fetch_json("/scoreboard")
        return data is not None
