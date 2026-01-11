"""Fighter endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    FighterDetail,
    FighterHistory,
    FighterListItem,
    FightersResponse,
    FighterStats,
    FightHistoryItem,
    PaginatedResponse,
)
from app.core.caching import cache_medium, cache_short
from app.core.exceptions import NotFoundException
from app.db.session import get_db
from app.repositories import FighterRepository, FightRepository

router = APIRouter(prefix="/fighters", tags=["Fighters"])


async def get_fighter_repo(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FighterRepository:
    """Dependency to get fighter repository."""
    return FighterRepository(db)


async def get_fight_repo(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FightRepository:
    """Dependency to get fight repository."""
    return FightRepository(db)


@router.get("", response_model=FightersResponse)
async def list_fighters(
    response: Response,
    repo: Annotated[FighterRepository, Depends(get_fighter_repo)],
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by name"),
    weight_class: str | None = Query(None, description="Filter by weight class"),
    active_only: bool = Query(True, description="Only active fighters"),
) -> FightersResponse:
    """List fighters with pagination and filters."""
    cache_short(response)  # 5 minute cache
    offset = (page - 1) * per_page

    if search:
        fighters = await repo.search(search, skip=offset, limit=per_page)
        total = await repo.count_search(search)
    elif weight_class:
        fighters = await repo.get_by_weight_class(
            weight_class,
            active_only=active_only,
            skip=offset,
            limit=per_page,
        )
        total = await repo.count_by_weight_class(weight_class, active_only)
    elif active_only:
        fighters = await repo.get_active_fighters(skip=offset, limit=per_page)
        total = await repo.count_active()
    else:
        fighters = await repo.get_all(skip=offset, limit=per_page)
        total = await repo.count()

    items = [
        FighterListItem(
            id=f.id,
            first_name=f.first_name,
            last_name=f.last_name,
            nickname=f.nickname,
            weight_class=f.weight_class,
            is_active=f.is_active,
            nationality=f.nationality,
            image_url=f.image_url,
        )
        for f in fighters
    ]

    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{fighter_id}", response_model=FighterDetail)
async def get_fighter(
    fighter_id: UUID,
    response: Response,
    repo: Annotated[FighterRepository, Depends(get_fighter_repo)],
) -> FighterDetail:
    """Get fighter details."""
    cache_medium(response)  # 1 hour cache
    fighter = await repo.get(fighter_id)

    if not fighter:
        raise NotFoundException("Fighter", str(fighter_id))

    return FighterDetail(
        id=fighter.id,
        first_name=fighter.first_name,
        last_name=fighter.last_name,
        nickname=fighter.nickname,
        weight_class=fighter.weight_class,
        is_active=fighter.is_active,
        date_of_birth=fighter.date_of_birth,
        nationality=fighter.nationality,
        hometown=fighter.hometown,
        height_cm=fighter.height_cm,
        weight_kg=fighter.weight_kg,
        reach_cm=fighter.reach_cm,
        leg_reach_cm=fighter.leg_reach_cm,
        stance=fighter.stance,
        ufc_profile_url=fighter.ufc_profile_url,
        image_url=fighter.image_url,
    )


@router.get("/{fighter_id}/stats", response_model=FighterStats)
async def get_fighter_stats(
    fighter_id: UUID,
    response: Response,
    repo: Annotated[FighterRepository, Depends(get_fighter_repo)],
) -> FighterStats:
    """Get fighter current statistics from latest snapshot."""
    cache_medium(response)  # 1 hour cache
    fighter = await repo.get(fighter_id)
    if not fighter:
        raise NotFoundException("Fighter", str(fighter_id))

    snapshot = await repo.get_latest_snapshot(fighter_id)

    if not snapshot:
        return FighterStats(fighter_id=fighter_id)

    return FighterStats(
        fighter_id=fighter_id,
        wins=snapshot.wins,
        losses=snapshot.losses,
        draws=snapshot.draws,
        no_contests=snapshot.no_contests,
        win_streak=snapshot.win_streak,
        loss_streak=snapshot.loss_streak,
        finish_rate=float(snapshot.finish_rate) if snapshot.finish_rate else None,
        ko_rate=float(snapshot.ko_rate) if snapshot.ko_rate else None,
        submission_rate=float(snapshot.submission_rate) if snapshot.submission_rate else None,
        striking_accuracy=float(snapshot.striking_accuracy) if snapshot.striking_accuracy else None,
        takedown_accuracy=float(snapshot.takedown_accuracy) if snapshot.takedown_accuracy else None,
        takedown_defense=float(snapshot.takedown_defense) if snapshot.takedown_defense else None,
        strike_defense=float(snapshot.strike_defense) if snapshot.strike_defense else None,
    )


@router.get("/{fighter_id}/history", response_model=FighterHistory)
async def get_fighter_history(
    fighter_id: UUID,
    response: Response,
    fighter_repo: Annotated[FighterRepository, Depends(get_fighter_repo)],
    fight_repo: Annotated[FightRepository, Depends(get_fight_repo)],
    limit: int = Query(20, ge=1, le=100, description="Maximum fights to return"),
) -> FighterHistory:
    """Get fighter's fight history."""
    cache_medium(response)  # 1 hour cache
    fighter = await fighter_repo.get(fighter_id)
    if not fighter:
        raise NotFoundException("Fighter", str(fighter_id))

    fights = await fight_repo.get_by_fighter(
        fighter_id,
        completed_only=True,
        limit=limit,
    )

    fight_items = []
    for fight in fights:
        is_fighter1 = fight.fighter1_id == fighter_id
        opponent = fight.fighter2 if is_fighter1 else fight.fighter1

        if fight.is_no_contest:
            result = "No Contest"
        elif fight.is_draw:
            result = "Draw"
        elif fight.winner_id == fighter_id:
            result = "Win"
        else:
            result = "Loss"

        fight_items.append(
            FightHistoryItem(
                fight_id=fight.id,
                event_name=fight.event.name if fight.event else "Unknown",
                event_date=fight.event.date if fight.event else None,
                opponent_name=opponent.full_name if opponent else "Unknown",
                opponent_id=opponent.id if opponent else None,
                weight_class=fight.weight_class,
                result=result,
                method=fight.result_method,
                ending_round=fight.ending_round,
                ending_time=fight.ending_time,
                is_title_fight=fight.is_title_fight,
                is_main_event=fight.is_main_event,
            )
        )

    return FighterHistory(
        fighter_id=fighter_id,
        fighter_name=fighter.full_name,
        fights=fight_items,
        total_fights=len(fight_items),
    )


@router.get("/search/{query}", response_model=list[FighterListItem])
async def search_fighters(
    query: str,
    response: Response,
    repo: Annotated[FighterRepository, Depends(get_fighter_repo)],
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
) -> list[FighterListItem]:
    """Search fighters by name or nickname."""
    cache_short(response)  # 5 minute cache
    fighters = await repo.search(query, limit=limit)

    return [
        FighterListItem(
            id=f.id,
            first_name=f.first_name,
            last_name=f.last_name,
            nickname=f.nickname,
            weight_class=f.weight_class,
            is_active=f.is_active,
            nationality=f.nationality,
            image_url=f.image_url,
        )
        for f in fighters
    ]
