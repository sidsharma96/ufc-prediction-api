"""UFC.com scraper adapter for fight card data.

Scrapes UFC.com event pages as a fallback when ESPN lacks fight card data.
Note: Uses BeautifulSoup for HTML parsing. Minimal scraping for fight cards only.
"""

import re
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.data_pipeline.adapters.base import (
    DataSourceAdapter,
    DataSourceType,
    RawEvent,
    RawFight,
    RawFighter,
)


def parse_ufc_date(date_str: str) -> date | None:
    """Parse UFC.com date format to date object.

    Args:
        date_str: Date string from UFC.com (e.g., "Jan 24, 2026")

    Returns:
        date object or None if parsing fails
    """
    if not date_str:
        return None

    # Clean up the string
    date_str = date_str.strip()

    # Common UFC.com formats
    formats = [
        "%b %d, %Y",  # Jan 24, 2026
        "%B %d, %Y",  # January 24, 2026
        "%Y-%m-%d",  # 2026-01-24
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
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

    # Clean up
    name = name.strip()

    parts = name.split(maxsplit=1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    return first_name, last_name


def normalize_weight_class(weight_class: str | None) -> str | None:
    """Normalize UFC.com weight class to standard format.

    Args:
        weight_class: Raw weight class text

    Returns:
        Normalized weight class name
    """
    if not weight_class:
        return None

    weight_class = weight_class.strip().lower()

    # Remove "bout" suffix
    weight_class = re.sub(r"\s*bout$", "", weight_class)

    # Remove title prefixes
    weight_class = re.sub(r"(interim\s+)?title\s*", "", weight_class)

    weight_class = weight_class.strip()

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


class UFCAdapter(DataSourceAdapter):
    """Adapter for scraping UFC.com fight cards.

    This adapter is used as a fallback when ESPN doesn't have
    complete fight card data for upcoming events.

    Note: Scraping is minimal - only fetches fight cards for
    events that ESPN has already identified.
    """

    BASE_URL = "https://www.ufc.com"

    def __init__(
        self,
        timeout: float = 30.0,
    ):
        """Initialize UFC adapter.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.UFC_SCRAPER

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch HTML from UFC.com.

        Args:
            url: Full URL to fetch

        Returns:
            HTML content as string, or None on error
        """
        client = await self._get_client()

        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            print(f"UFC.com scraper error: {e}")
            return None

    async def fetch_event_by_slug(self, slug: str) -> RawEvent | None:
        """Fetch a single event by its URL slug.

        Args:
            slug: Event slug (e.g., "ufc-324")

        Returns:
            RawEvent or None if not found
        """
        url = f"{self.BASE_URL}/event/{slug}"
        html = await self._fetch_html(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        return self._parse_event_page(soup, slug, url)

    def _parse_event_page(
        self,
        soup: BeautifulSoup,
        slug: str,
        source_url: str,
    ) -> RawEvent | None:
        """Parse event page HTML.

        Args:
            soup: BeautifulSoup parsed page
            slug: Event slug
            source_url: Source URL for metadata

        Returns:
            RawEvent or None if parsing fails
        """
        try:
            # Get event name from page title or header
            title_tag = soup.find("h1") or soup.find("title")
            if not title_tag:
                return None

            name = title_tag.get_text(strip=True)
            # Clean up title
            name = re.sub(r"\s*\|.*$", "", name)  # Remove " | UFC.com" suffix

            # Get event date - look for date elements
            date_elem = soup.find(class_=re.compile(r"date|event.*date", re.I))
            event_date = None
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                event_date = parse_ufc_date(date_text)

            # If no date found, try to extract from page content
            if not event_date:
                # Look for date pattern in page
                date_pattern = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}"
                date_match = re.search(date_pattern, soup.get_text())
                if date_match:
                    event_date = parse_ufc_date(date_match.group())

            if not event_date:
                return None

            # Get venue info
            venue_elem = soup.find(class_=re.compile(r"venue|location", re.I))
            venue = None
            city = None
            country = None

            if venue_elem:
                venue_text = venue_elem.get_text(strip=True)
                # Parse "T-Mobile Arena, Las Vegas, NV" format
                parts = [p.strip() for p in venue_text.split(",")]
                if len(parts) >= 1:
                    venue = parts[0]
                if len(parts) >= 2:
                    city = parts[1]
                if len(parts) >= 3:
                    country = parts[-1]

            # Determine event type
            event_type = None
            name_lower = name.lower()
            if re.search(r"ufc\s+\d+", name_lower):
                event_type = "numbered"
            elif "fight night" in name_lower:
                event_type = "fight_night"

            return RawEvent(
                name=name,
                event_date=event_date,
                venue=venue,
                city=city,
                country=country,
                event_type=event_type,
                is_completed=False,
                ufc_id=slug,
                source=DataSourceType.UFC_SCRAPER,
                source_url=source_url,
            )

        except Exception as e:
            print(f"Error parsing UFC event page: {e}")
            return None

    def _event_name_to_slug(self, event_name: str) -> str | None:
        """Convert event name to UFC.com URL slug.

        Args:
            event_name: Event name like "UFC 324" or "UFC 324: Gaethje vs. Pimblett"

        Returns:
            URL slug like "ufc-324" or None if can't extract
        """
        if not event_name:
            return None

        # Try to extract "UFC <number>" pattern
        match = re.search(r"ufc\s*(\d+)", event_name.lower())
        if match:
            return f"ufc-{match.group(1)}"

        # Try Fight Night pattern
        match = re.search(r"fight\s*night", event_name.lower())
        if match:
            # Fight Nights use different slugs - harder to guess
            return None

        return None

    async def fetch_fight_card(
        self,
        event_name_or_slug: str,
    ) -> list[RawFight]:
        """Fetch fight card for a specific event.

        Args:
            event_name_or_slug: Event name (e.g., "UFC 324: Gaethje vs. Pimblett")
                               or slug (e.g., "ufc-324")

        Returns:
            List of fights on the card
        """
        # Convert name to slug if needed
        slug = event_name_or_slug
        if not slug.startswith("ufc-"):
            slug = self._event_name_to_slug(event_name_or_slug)
            if not slug:
                return []

        url = f"{self.BASE_URL}/event/{slug}"
        html = await self._fetch_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        return self._parse_fight_card(soup, slug)

    def _parse_fight_card(
        self,
        soup: BeautifulSoup,
        event_slug: str,
    ) -> list[RawFight]:
        """Parse fight card from event page.

        Args:
            soup: BeautifulSoup parsed page
            event_slug: Event slug for metadata

        Returns:
            List of RawFight objects
        """
        # Get event name and date for the fights
        event = self._parse_event_page(soup, event_slug, "")
        event_name = event.name if event else None
        event_date = event.event_date if event else None

        # Use fallback parsing which works better with UFC.com structure
        fights = self._parse_fight_card_fallback(soup, event_name, event_date)

        def get_last_name(name: str) -> str:
            """Extract last name from full name."""
            parts = name.lower().strip().split()
            return parts[-1] if parts else ""

        # First pass: collect valid fights with complete names
        valid_fights: list[RawFight] = []
        for fight in fights:
            f1_parts = fight.fighter1_name.split()
            f2_parts = fight.fighter2_name.split()
            # Require at least first + last name
            if len(f1_parts) >= 2 and len(f2_parts) >= 2:
                valid_fights.append(fight)

        # Second pass: deduplicate by last names, keep first occurrence
        unique_fights: list[RawFight] = []
        seen_matchups: set[frozenset[str]] = set()

        for fight in valid_fights:
            last1 = get_last_name(fight.fighter1_name)
            last2 = get_last_name(fight.fighter2_name)

            if not last1 or not last2 or last1 == last2:
                continue

            matchup = frozenset([last1, last2])

            if matchup in seen_matchups:
                continue

            seen_matchups.add(matchup)
            unique_fights.append(fight)

        # Re-number fight order
        total = len(unique_fights)
        for i, fight in enumerate(unique_fights):
            fight.fight_order = total - i
            fight.is_main_event = fight.fight_order == 1
            if fight.is_main_event or fight.is_title_fight:
                fight.scheduled_rounds = 5

        return unique_fights

    def _parse_fight_container(
        self,
        container: Any,
        fight_order: int,
        event_name: str | None,
        event_date: date | None,
    ) -> RawFight | None:
        """Parse a single fight container.

        Args:
            container: BeautifulSoup element containing fight data
            fight_order: Order on card (1 = main event)
            event_name: Event name
            event_date: Event date

        Returns:
            RawFight or None if parsing fails
        """
        try:
            # Find fighter names - look for linked names
            fighter_links = container.find_all("a", href=re.compile(r"/athlete/"))
            if len(fighter_links) < 2:
                # Try finding by text content
                text = container.get_text(separator="\n")
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                # Look for "vs" pattern
                for i, line in enumerate(lines):
                    if line.lower() == "vs" and i > 0 and i < len(lines) - 1:
                        fighter1_name = lines[i - 1]
                        fighter2_name = lines[i + 1]
                        break
                else:
                    return None
            else:
                fighter1_name = fighter_links[0].get_text(strip=True)
                fighter2_name = fighter_links[1].get_text(strip=True)

            # Clean fighter names
            fighter1_name = re.sub(r"#\d+\s*", "", fighter1_name).strip()
            fighter2_name = re.sub(r"#\d+\s*", "", fighter2_name).strip()

            if not fighter1_name or not fighter2_name:
                return None

            # Get weight class
            weight_class = "Unknown"
            weight_elem = container.find(
                class_=re.compile(r"weight|division|class", re.I)
            )
            if weight_elem:
                weight_class = normalize_weight_class(
                    weight_elem.get_text(strip=True)
                ) or "Unknown"

            # Check for title fight
            text_content = container.get_text().lower()
            is_title = "title" in text_content

            # Main event is fight_order == 1
            is_main = fight_order == 1

            # Scheduled rounds
            scheduled_rounds = 5 if is_title or is_main else 3

            return RawFight(
                fighter1_name=fighter1_name,
                fighter2_name=fighter2_name,
                weight_class=weight_class,
                event_name=event_name,
                event_date=event_date,
                is_title_fight=is_title,
                is_main_event=is_main,
                scheduled_rounds=scheduled_rounds,
                fight_order=fight_order,
                source=DataSourceType.UFC_SCRAPER,
            )

        except Exception as e:
            print(f"Error parsing fight container: {e}")
            return None

    def _parse_fight_card_fallback(
        self,
        soup: BeautifulSoup,
        event_name: str | None,
        event_date: date | None,
    ) -> list[RawFight]:
        """Fallback parsing using text patterns.

        Args:
            soup: BeautifulSoup parsed page
            event_name: Event name
            event_date: Event date

        Returns:
            List of fights found
        """
        fights: list[RawFight] = []

        # Get all text and look for "vs" patterns
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Filter out very short lines and clean up
        cleaned_lines = []
        for line in lines:
            # Skip very short or irrelevant lines
            if len(line) < 2:
                continue
            # Skip navigation/menu items
            if line.lower() in ["home", "news", "watch", "athletes", "rankings", "events"]:
                continue
            cleaned_lines.append(line)

        lines = cleaned_lines
        fight_order = 0
        i = 0

        while i < len(lines) - 2:
            if lines[i + 1].lower() == "vs":
                # Clean fighter names - remove rankings like #4, #5
                fighter1_raw = lines[i]
                fighter2_raw = lines[i + 2]

                # Remove ranking numbers
                fighter1_name = re.sub(r"#\d+\s*", "", fighter1_raw).strip()
                fighter2_name = re.sub(r"#\d+\s*", "", fighter2_raw).strip()

                # Add space between concatenated names (JustinGaethje -> Justin Gaethje)
                fighter1_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", fighter1_name)
                fighter2_name = re.sub(r"([a-z])([A-Z])", r"\1 \2", fighter2_name)

                # Skip if names are too short
                if len(fighter1_name) < 3 or len(fighter2_name) < 3:
                    i += 1
                    continue

                # Try to get weight class from nearby lines
                weight_class = "Unknown"
                is_title = False
                for j in range(max(0, i - 3), min(len(lines), i + 5)):
                    line_lower = lines[j].lower()
                    if any(w in line_lower for w in [
                        "flyweight", "bantamweight", "featherweight",
                        "lightweight", "welterweight", "middleweight",
                        "heavyweight", "strawweight"
                    ]):
                        weight_class = normalize_weight_class(lines[j]) or "Unknown"
                        if "title" in line_lower:
                            is_title = True
                        break

                fight_order += 1
                fights.append(RawFight(
                    fighter1_name=fighter1_name,
                    fighter2_name=fighter2_name,
                    weight_class=weight_class,
                    event_name=event_name,
                    event_date=event_date,
                    is_title_fight=is_title,
                    is_main_event=False,
                    scheduled_rounds=5 if is_title else 3,
                    fight_order=fight_order,
                    source=DataSourceType.UFC_SCRAPER,
                ))
                i += 3
            else:
                i += 1

        return fights

    async def fetch_fighters(self) -> list[RawFighter]:
        """Fetch fighters - extracted from fight cards.

        Returns:
            List of fighters from scraped events
        """
        # Not implemented for scraper - fighters extracted from fights
        return []

    async def fetch_events(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawEvent]:
        """Fetch events from UFC.com.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of events
        """
        # Scraper is used for specific events, not listing
        return []

    async def fetch_upcoming_events(self) -> list[RawEvent]:
        """Fetch upcoming events from UFC.com.

        Returns:
            List of upcoming events
        """
        url = f"{self.BASE_URL}/events"
        html = await self._fetch_html(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        events: list[RawEvent] = []

        # Find event links
        event_links = soup.find_all("a", href=re.compile(r"/event/ufc-\d+"))
        seen_slugs: set[str] = set()

        for link in event_links:
            href = link.get("href", "")
            # Extract slug
            match = re.search(r"/event/(ufc-\d+)", href)
            if match:
                slug = match.group(1)
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    event = await self.fetch_event_by_slug(slug)
                    if event and event.event_date >= date.today():
                        events.append(event)

        return events

    async def fetch_fights(
        self,
        event_name: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RawFight]:
        """Fetch fights from UFC.com.

        Args:
            event_name: Optional event name filter
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of fights
        """
        # Scraper is used for specific events via fetch_fight_card
        return []

    async def health_check(self) -> bool:
        """Check if UFC.com is accessible."""
        html = await self._fetch_html(f"{self.BASE_URL}/events")
        return html is not None
