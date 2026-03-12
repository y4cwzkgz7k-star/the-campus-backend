import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.match import Match, MatchPlayer
from app.models.user import User
from app.schemas.match import CreateMatchRequest, MatchOut, MatchPlayerOut

router = APIRouter(prefix="/matches", tags=["matches"])


def _build_match_out(match: Match) -> MatchOut:
    players = [
        MatchPlayerOut(
            user_id=mp.user_id,
            display_name=mp.user.profile.display_name if mp.user and mp.user.profile else "",
            avatar_url=mp.user.profile.avatar_url if mp.user and mp.user.profile else None,
            status=mp.status,
        )
        for mp in match.players
    ]
    return MatchOut(
        id=match.id,
        sport_id=match.sport_id,
        format=match.format,
        status=match.status,
        max_players=match.max_players,
        scheduled_at=match.scheduled_at,
        notes=match.notes,
        city=match.city,
        created_at=match.created_at,
        players=players,
    )


@router.get("/", response_model=list[MatchOut])
async def list_matches(
    sport_id: uuid.UUID | None = None,
    city: str | None = None,
    status: str = "open",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = (
        select(Match)
        .where(Match.status == status)
        .options(
            selectinload(Match.players)
            .selectinload(MatchPlayer.user)
            .selectinload(User.profile)
        )
        .order_by(Match.scheduled_at.asc().nullslast(), Match.created_at.desc())
    )
    if sport_id:
        query = query.where(Match.sport_id == sport_id)
    if city:
        query = query.where(Match.city.ilike(f"%{city}%"))

    result = await db.execute(query.limit(50))
    return [_build_match_out(m) for m in result.scalars().all()]


@router.post("/", response_model=MatchOut, status_code=201)
async def create_match(
    body: CreateMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    match = Match(
        sport_id=body.sport_id,
        booking_id=body.booking_id,
        created_by=current_user.id,
        format=body.format,
        max_players=body.max_players,
        scheduled_at=body.scheduled_at,
        notes=body.notes,
        city=body.city or (current_user.profile.city if current_user.profile else None),
    )
    db.add(match)
    await db.flush()

    db.add(MatchPlayer(match_id=match.id, user_id=current_user.id, status="confirmed"))
    await db.commit()

    result = await db.execute(
        select(Match)
        .where(Match.id == match.id)
        .options(
            selectinload(Match.players)
            .selectinload(MatchPlayer.user)
            .selectinload(User.profile)
        )
    )
    return _build_match_out(result.scalar_one())


@router.post("/{match_id}/join", response_model=MatchOut)
async def join_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Match)
        .where(Match.id == match_id)
        .with_for_update()
        .options(selectinload(Match.players).selectinload(MatchPlayer.user).selectinload(User.profile))
    )
    match = result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status != "open":
        raise HTTPException(status_code=409, detail="Match is not open")

    confirmed = [p for p in match.players if p.status == "confirmed"]
    if len(confirmed) >= match.max_players:
        raise HTTPException(status_code=409, detail="Match is full")

    already = any(p.user_id == current_user.id for p in match.players)
    if already:
        raise HTTPException(status_code=400, detail="Already joined")

    db.add(MatchPlayer(match_id=match.id, user_id=current_user.id, status="confirmed"))

    if len(confirmed) + 1 >= match.max_players:
        match.status = "full"

    await db.commit()

    result = await db.execute(
        select(Match)
        .where(Match.id == match_id)
        .options(selectinload(Match.players).selectinload(MatchPlayer.user).selectinload(User.profile))
    )
    return _build_match_out(result.scalar_one())


@router.delete("/{match_id}/leave", status_code=204)
async def leave_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MatchPlayer).where(
            MatchPlayer.match_id == match_id,
            MatchPlayer.user_id == current_user.id,
        )
    )
    mp = result.scalar_one_or_none()
    if not mp:
        raise HTTPException(status_code=404, detail="Not in this match")

    await db.delete(mp)

    match_result = await db.execute(select(Match).where(Match.id == match_id).with_for_update())
    match = match_result.scalar_one_or_none()
    if match and match.status == "full":
        match.status = "open"

    await db.commit()
