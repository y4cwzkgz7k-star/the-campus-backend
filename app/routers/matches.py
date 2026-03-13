import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.match import Match, MatchPlayer
from app.models.user import User, UserProfile
from app.schemas.match import (
    CreateMatchRequest,
    MatchOut,
    MatchPlayerOut,
    MatchResultOut,
    MatchResultRequest,
    PlayerEloOut,
)

router = APIRouter(prefix="/matches", tags=["matches"])

ELO_K = 32
ELO_DEFAULT_RATING = 1200.0


def _compute_elo(rating_a: float, rating_b: float, score_a: int, score_b: int) -> tuple[float, float]:
    """Return (new_rating_a, new_rating_b) using standard Elo formula."""
    expected_a = 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))
    expected_b = 1.0 - expected_a

    if score_a > score_b:
        actual_a, actual_b = 1.0, 0.0
    elif score_b > score_a:
        actual_a, actual_b = 0.0, 1.0
    else:
        actual_a, actual_b = 0.5, 0.5

    new_rating_a = rating_a + ELO_K * (actual_a - expected_a)
    new_rating_b = rating_b + ELO_K * (actual_b - expected_b)
    return round(new_rating_a, 2), round(new_rating_b, 2)


def _build_match_out(match: Match) -> MatchOut:
    players = [
        MatchPlayerOut(
            id=mp.user_id,
            display_name=mp.user.profile.display_name if mp.user and mp.user.profile else "",
            avatar_url=mp.user.profile.avatar_url if mp.user and mp.user.profile else None,
            status=mp.status,
            rating=mp.user.profile.rating if mp.user and mp.user.profile else None,
        )
        for mp in match.players
    ]
    return MatchOut(
        id=match.id,
        sport_id=match.sport_id,
        title=match.title,
        format=match.format,
        status=match.status,
        max_players=match.max_players,
        current_players=len(players),
        created_by=match.created_by,
        scheduled_at=match.scheduled_at,
        notes=match.notes,
        city=match.city,
        created_at=match.created_at,
        score_home=match.score_home,
        score_away=match.score_away,
        result_source=match.result_source,
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
        safe_city = city.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Match.city.ilike(f"%{safe_city}%", escape="\\"))

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
        title=body.title,
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


@router.post("/{match_id}/result", response_model=MatchResultOut)
async def submit_result(
    match_id: uuid.UUID,
    body: MatchResultRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Load match with players
    match_result = await db.execute(
        select(Match)
        .where(Match.id == match_id)
        .with_for_update()
        .options(
            selectinload(Match.players)
            .selectinload(MatchPlayer.user)
            .selectinload(User.profile)
        )
    )
    match = match_result.scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Verify current user is a confirmed participant
    participant_ids = {mp.user_id for mp in match.players if mp.status == "confirmed"}
    if current_user.id not in participant_ids:
        raise HTTPException(status_code=403, detail="Only match participants can submit results")

    if match.status == "completed":
        raise HTTPException(status_code=409, detail="Result already submitted for this match")

    if match.status not in ("open", "full", "in_progress"):
        raise HTTPException(status_code=409, detail=f"Cannot submit result for match with status '{match.status}'")

    # For ELO we need exactly 2 players (singles) or treat first two as representatives
    confirmed_players = [mp for mp in match.players if mp.status == "confirmed"]
    if len(confirmed_players) < 2:
        raise HTTPException(status_code=400, detail="Match needs at least 2 confirmed players to submit result")

    # player_a = creator (home), player_b = first other confirmed player (away)
    home_mp = next((mp for mp in confirmed_players if mp.user_id == match.created_by), confirmed_players[0])
    away_mp = next((mp for mp in confirmed_players if mp.user_id != home_mp.user_id), None)
    if away_mp is None:
        raise HTTPException(status_code=400, detail="Cannot determine two distinct players for ELO calculation")

    # Load profiles with for_update to update ratings
    home_profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == home_mp.user_id).with_for_update()
    )
    home_profile = home_profile_result.scalar_one_or_none()

    away_profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == away_mp.user_id).with_for_update()
    )
    away_profile = away_profile_result.scalar_one_or_none()

    if not home_profile or not away_profile:
        raise HTTPException(status_code=500, detail="Player profile not found")

    rating_a = home_profile.rating if home_profile.rating is not None else ELO_DEFAULT_RATING
    rating_b = away_profile.rating if away_profile.rating is not None else ELO_DEFAULT_RATING

    new_rating_a, new_rating_b = _compute_elo(rating_a, rating_b, body.score_home, body.score_away)

    # Update match — create new state without mutating nested objects
    match.score_home = body.score_home
    match.score_away = body.score_away
    match.status = "completed"

    # Update ELO ratings
    home_profile.rating = new_rating_a
    away_profile.rating = new_rating_b

    await db.commit()

    # Re-fetch match for clean response
    refreshed_result = await db.execute(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.players)
            .selectinload(MatchPlayer.user)
            .selectinload(User.profile)
        )
    )
    refreshed_match = refreshed_result.scalar_one()

    return MatchResultOut(
        match=_build_match_out(refreshed_match),
        player_a=PlayerEloOut(user_id=home_mp.user_id, new_rating=new_rating_a),
        player_b=PlayerEloOut(user_id=away_mp.user_id, new_rating=new_rating_b),
    )
