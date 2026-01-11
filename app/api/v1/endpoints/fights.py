"""Fight endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    FightDetail,
    FighterBrief,
    FighterSnapshotBrief,
    FightListItem,
    FightsResponse,
    PaginatedResponse,
)
from app.core.caching import cache_medium, cache_short
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.repositories import FightRepository

router = APIRouter(prefix="/fights", tags=["Fights"])


async def get_fight_repo(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FightRepository:
    """Dependency to get fight repository."""
    return FightRepository(db)


@router.get("", response_model=FightsResponse)
async def list_fights(
    response: Response,
    repo: Annotated[FightRepository, Depends(get_fight_repo)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    upcoming: bool = Query(False, description="Only upcoming fights"),
) -> FightsResponse:
    """List fights with pagination and filters."""
    cache_short(response)  # 5 minute cache
    offset = (page - 1) * per_page

    if upcoming:
        fights = await repo.get_upcoming(skip=offset, limit=per_page)
        total = await repo.count_upcoming()
    else:
        fights = await repo.get_all_with_details(skip=offset, limit=per_page)
        total = await repo.count()

    items = []
    for f in fights:
        items.append(
            FightListItem(
                id=f.id,
                weight_class=f.weight_class,
                is_title_fight=f.is_title_fight,
                is_main_event=f.is_main_event,
                scheduled_rounds=f.scheduled_rounds,
                status=f.status,
                event_id=f.event_id,
                event_name=f.event.name if f.event else "Unknown",
                event_date=f.event.date if f.event else None,
                fighter1_name=f.fighter1.full_name if f.fighter1 else "TBA",
                fighter2_name=f.fighter2.full_name if f.fighter2 else "TBA",
                winner_name=f.winner.full_name if f.winner else None,
                result_method=f.result_method,
            )
        )

    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/upcoming", response_model=list[FightListItem])
async def get_upcoming_fights(
    response: Response,
    repo: Annotated[FightRepository, Depends(get_fight_repo)],
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
) -> list[FightListItem]:
    """Get upcoming scheduled fights."""
    cache_short(response)  # 5 minute cache
    fights = await repo.get_upcoming(limit=limit)

    return [
        FightListItem(
            id=f.id,
            weight_class=f.weight_class,
            is_title_fight=f.is_title_fight,
            is_main_event=f.is_main_event,
            scheduled_rounds=f.scheduled_rounds,
            status=f.status,
            event_id=f.event_id,
            event_name=f.event.name if f.event else "Unknown",
            event_date=f.event.date if f.event else None,
            fighter1_name=f.fighter1.full_name if f.fighter1 else "TBA",
            fighter2_name=f.fighter2.full_name if f.fighter2 else "TBA",
            winner_name=None,
            result_method=None,
        )
        for f in fights
    ]


@router.get("/{fight_id}", response_model=FightDetail)
async def get_fight(
    fight_id: UUID,
    response: Response,
    repo: Annotated[FightRepository, Depends(get_fight_repo)],
) -> FightDetail:
    """Get fight details with fighters and snapshots."""
    cache_medium(response)  # 1 hour cache
    fight = await repo.get_with_details(fight_id)

    if not fight:
        raise NotFoundException("Fight", str(fight_id))

    # Get snapshots for each fighter using O(1) lookup
    snapshot_map = {s.fighter_id: s for s in fight.snapshots}

    fighter1_snapshot = None
    fighter2_snapshot = None

    if f1_snap := snapshot_map.get(fight.fighter1_id):
        fighter1_snapshot = FighterSnapshotBrief(
            wins=f1_snap.wins,
            losses=f1_snap.losses,
            draws=f1_snap.draws,
            win_streak=f1_snap.win_streak,
            loss_streak=f1_snap.loss_streak,
            finish_rate=float(f1_snap.finish_rate) if f1_snap.finish_rate else None,
        )

    if f2_snap := snapshot_map.get(fight.fighter2_id):
        fighter2_snapshot = FighterSnapshotBrief(
            wins=f2_snap.wins,
            losses=f2_snap.losses,
            draws=f2_snap.draws,
            win_streak=f2_snap.win_streak,
            loss_streak=f2_snap.loss_streak,
            finish_rate=float(f2_snap.finish_rate) if f2_snap.finish_rate else None,
        )

    return FightDetail(
        id=fight.id,
        weight_class=fight.weight_class,
        is_title_fight=fight.is_title_fight,
        is_main_event=fight.is_main_event,
        is_co_main_event=fight.is_co_main_event,
        scheduled_rounds=fight.scheduled_rounds,
        status=fight.status,
        fight_order=fight.fight_order,
        event_id=fight.event_id,
        event_name=fight.event.name if fight.event else "Unknown",
        event_date=fight.event.date if fight.event else None,
        fighter1=FighterBrief(
            id=fight.fighter1.id,
            first_name=fight.fighter1.first_name,
            last_name=fight.fighter1.last_name,
            nickname=fight.fighter1.nickname,
            image_url=fight.fighter1.image_url,
        ) if fight.fighter1 else None,
        fighter2=FighterBrief(
            id=fight.fighter2.id,
            first_name=fight.fighter2.first_name,
            last_name=fight.fighter2.last_name,
            nickname=fight.fighter2.nickname,
            image_url=fight.fighter2.image_url,
        ) if fight.fighter2 else None,
        fighter1_snapshot=fighter1_snapshot,
        fighter2_snapshot=fighter2_snapshot,
        winner_id=fight.winner_id,
        result_method=fight.result_method,
        result_method_detail=fight.result_method_detail,
        ending_round=fight.ending_round,
        ending_time=fight.ending_time,
        is_no_contest=fight.is_no_contest,
        is_draw=fight.is_draw,
    )


@router.get("/head-to-head/{fighter1_id}/{fighter2_id}", response_model=list[FightListItem])
async def get_head_to_head(
    fighter1_id: UUID,
    fighter2_id: UUID,
    response: Response,
    repo: Annotated[FightRepository, Depends(get_fight_repo)],
) -> list[FightListItem]:
    """Get all fights between two fighters."""
    cache_medium(response)  # 1 hour cache (historical data)
    fights = await repo.get_head_to_head(fighter1_id, fighter2_id)

    return [
        FightListItem(
            id=f.id,
            weight_class=f.weight_class,
            is_title_fight=f.is_title_fight,
            is_main_event=f.is_main_event,
            scheduled_rounds=f.scheduled_rounds,
            status=f.status,
            event_id=f.event_id,
            event_name=f.event.name if f.event else "Unknown",
            event_date=f.event.date if f.event else None,
            fighter1_name=f.fighter1.full_name if f.fighter1 else "TBA",
            fighter2_name=f.fighter2.full_name if f.fighter2 else "TBA",
            winner_name=f.winner.full_name if f.winner else None,
            result_method=f.result_method,
        )
        for f in fights
    ]
