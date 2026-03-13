import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.club import Club
from app.models.court import Court, CourtSlot
from app.models.user import User
from app.schemas.club import ClubOut, SlotOut

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("/", response_model=list[ClubOut])
async def list_clubs(
    city: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Club)
        .where(Club.is_active == True)
        .options(selectinload(Club.courts))
        .order_by(Club.name)
    )
    if city:
        safe_city = city.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Club.city.ilike(f"%{safe_city}%", escape="\\"))

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{slug}", response_model=ClubOut)
async def get_club(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Club)
        .where(Club.slug == slug, Club.is_active == True)
        .options(selectinload(Club.courts))
    )
    club = result.scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    return club


@router.get("/{slug}/slots", response_model=list[SlotOut])
async def get_club_slots(
    slug: str,
    slot_date: date | None = None,
    sport_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    club_result = await db.execute(select(Club).where(Club.slug == slug))
    club = club_result.scalar_one_or_none()
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")

    query = (
        select(CourtSlot)
        .join(CourtSlot.court)
        .where(
            Court.club_id == club.id,
            CourtSlot.status == "available",
        )
        .options(selectinload(CourtSlot.court))
    )
    if slot_date:
        query = query.where(CourtSlot.slot_date == slot_date)
    if sport_id:
        query = query.where(Court.sport_id == sport_id)

    result = await db.execute(query.order_by(CourtSlot.slot_date, CourtSlot.start_time))
    slots = result.scalars().all()

    return [
        SlotOut(
            id=s.id,
            court_id=s.court_id,
            slot_date=s.slot_date,
            start_time=s.start_time,
            end_time=s.end_time,
            status=s.status,
            price=float(s.price_override or s.court.price_per_hour),
        )
        for s in slots
    ]
