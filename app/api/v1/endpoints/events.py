"""Event endpoints."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    EventDetail,
    EventListItem,
    EventsResponse,
    FightSummary,
    PaginatedResponse,
    UpcomingEvent,
)
from app.core.caching import cache_medium, cache_short
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.repositories import EventRepository

router = APIRouter(prefix="/events", tags=["Events"])


async def get_event_repo(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EventRepository:
    """Dependency to get event repository."""
    return EventRepository(db)


@router.get("", response_model=EventsResponse)
async def list_events(
    response: Response,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    completed: bool | None = Query(None, description="Filter by completed status"),
    from_date: date | None = Query(None, description="Filter from date"),
    to_date: date | None = Query(None, description="Filter to date"),
) -> EventsResponse:
    """List events with pagination and filters."""
    cache_short(response)  # 5 minute cache
    offset = (page - 1) * per_page

    if from_date and to_date:
        events = await repo.get_by_date_range(
            from_date=from_date,
            to_date=to_date,
            skip=offset,
            limit=per_page,
        )
        total = await repo.count_by_date_range(from_date, to_date)
    elif completed is True:
        events = await repo.get_completed(skip=offset, limit=per_page)
        total = await repo.count_completed()
    elif completed is False:
        events = await repo.get_upcoming(limit=per_page)
        total = await repo.count_upcoming()
    else:
        events = await repo.get_all(skip=offset, limit=per_page)
        total = await repo.count()

    items = [
        EventListItem(
            id=e.id,
            name=e.name,
            date=e.date,
            venue=e.venue,
            city=e.city,
            country=e.country,
            is_completed=e.is_completed,
            event_type=e.event_type,
            fight_count=e.fight_count,
            poster_url=e.poster_url,
        )
        for e in events
    ]

    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/upcoming", response_model=list[UpcomingEvent])
async def get_upcoming_events(
    response: Response,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    limit: int = Query(5, ge=1, le=20, description="Number of events"),
) -> list[UpcomingEvent]:
    """Get upcoming UFC events."""
    cache_short(response)  # 5 minute cache
    events = await repo.get_upcoming(limit=limit, include_fights=True)

    result = []
    for event in events:
        main_event = event.main_event
        main_matchup = None
        if main_event:
            main_matchup = main_event.matchup

        result.append(
            UpcomingEvent(
                id=event.id,
                name=event.name,
                date=event.date,
                venue=event.venue,
                city=event.city,
                country=event.country,
                is_completed=event.is_completed,
                event_type=event.event_type,
                poster_url=event.poster_url,
                main_event_matchup=main_matchup,
                fight_count=event.fight_count,
            )
        )

    return result


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(
    event_id: UUID,
    response: Response,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
) -> EventDetail:
    """Get event details with fights."""
    cache_medium(response)  # 1 hour cache
    event = await repo.get_with_fights(event_id)

    if not event:
        raise NotFoundException("Event", str(event_id))

    fights = [
        FightSummary(
            id=f.id,
            fighter1_name=f.fighter1.full_name if f.fighter1 else "TBA",
            fighter2_name=f.fighter2.full_name if f.fighter2 else "TBA",
            weight_class=f.weight_class,
            is_title_fight=f.is_title_fight,
            is_main_event=f.is_main_event,
            status=f.status,
            winner_name=f.winner.full_name if f.winner else None,
            result_method=f.result_method,
        )
        for f in event.fights
    ]

    return EventDetail(
        id=event.id,
        name=event.name,
        date=event.date,
        venue=event.venue,
        city=event.city,
        country=event.country,
        state=event.state,
        is_completed=event.is_completed,
        short_name=event.short_name,
        event_type=event.event_type,
        start_time=event.start_time,
        is_cancelled=event.is_cancelled,
        poster_url=event.poster_url,
        fights=fights,
    )


@router.get("/search/{query}", response_model=list[EventListItem])
async def search_events(
    query: str,
    response: Response,
    repo: Annotated[EventRepository, Depends(get_event_repo)],
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
) -> list[EventListItem]:
    """Search events by name."""
    cache_short(response)  # 5 minute cache
    events = await repo.search_by_name(query, limit=limit)

    return [
        EventListItem(
            id=e.id,
            name=e.name,
            date=e.date,
            venue=e.venue,
            city=e.city,
            country=e.country,
            is_completed=e.is_completed,
            event_type=e.event_type,
            fight_count=e.fight_count,
            poster_url=e.poster_url,
        )
        for e in events
    ]
