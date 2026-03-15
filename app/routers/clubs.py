import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.booking import Booking
from app.models.club import Club
from app.models.club_member import ClubMember
from app.models.court import Court, CourtSlot
from app.models.user import User
from app.schemas.club import ClubOut, CourtOut, SlotOut
from app.schemas.invite import AddCourtRequest, ClubSetupRequest, MyClubOut

router = APIRouter(prefix="/clubs", tags=["clubs"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


async def _get_owner_membership(db: AsyncSession, user_id: uuid.UUID) -> ClubMember:
    """Return the caller's owner ClubMember or raise 403."""
    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.user_id == user_id, ClubMember.role == "owner")
        .options(selectinload(ClubMember.club))
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a club owner to perform this action",
        )
    return membership


async def _get_any_membership(db: AsyncSession, user_id: uuid.UUID) -> ClubMember:
    """Return the caller's ClubMember (owner or manager) or raise 403."""
    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.user_id == user_id)
        .options(selectinload(ClubMember.club))
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of any club",
        )
    return membership


# ---------------------------------------------------------------------------
# Self-service endpoints — declared BEFORE /{slug} to avoid routing conflict
# ---------------------------------------------------------------------------


@router.get("/my", response_model=list[MyClubOut])
async def list_my_clubs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MyClubOut]:
    """Return all clubs the authenticated user belongs to via ClubMember."""
    if current_user.role not in ("club_owner", "club_manager", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club owners and managers can access this endpoint",
        )

    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.user_id == current_user.id)
        .options(selectinload(ClubMember.club))
    )
    memberships = result.scalars().all()

    return [
        MyClubOut(
            id=m.club.id,
            name=m.club.name,
            slug=m.club.slug,
            address=m.club.address,
            city=m.club.city,
            phone=m.club.phone,
            description=m.club.description,
            is_verified=m.club.is_verified,
            member_role=m.role,
        )
        for m in memberships
    ]


@router.put("/my/setup", response_model=MyClubOut)
async def setup_my_club(
    body: ClubSetupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MyClubOut:
    """Update club details. Caller must be the club owner."""
    if current_user.role not in ("club_owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club owners can update club details",
        )

    membership = await _get_owner_membership(db, current_user.id)
    club = membership.club

    club.name = body.name
    club.address = body.address
    club.city = body.city
    club.phone = body.phone
    club.description = body.description

    await db.commit()
    await db.refresh(club)

    return MyClubOut(
        id=club.id,
        name=club.name,
        slug=club.slug,
        address=club.address,
        city=club.city,
        phone=club.phone,
        description=club.description,
        is_verified=club.is_verified,
        member_role=membership.role,
    )


@router.post("/my/courts", response_model=CourtOut, status_code=status.HTTP_201_CREATED)
async def add_court_to_my_club(
    body: AddCourtRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CourtOut:
    """Add a new court to the caller's club. Caller must be the club owner."""
    if current_user.role not in ("club_owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club owners can add courts",
        )

    membership = await _get_owner_membership(db, current_user.id)

    court = Court(
        club_id=membership.club_id,
        sport_id=body.sport_id,
        name=body.name,
        surface=body.surface,
        is_indoor=body.is_indoor,
        price_per_hour=body.price_per_hour,
        currency=body.currency,
    )
    db.add(court)
    await db.commit()
    await db.refresh(court)

    return CourtOut(
        id=court.id,
        name=court.name,
        sport_id=court.sport_id,
        surface=court.surface,
        is_indoor=court.is_indoor,
        price_per_hour=float(court.price_per_hour),
        currency=court.currency,
    )


@router.get("/my/courts", response_model=list[CourtOut])
async def list_my_courts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CourtOut]:
    """List courts for the caller's club. Owner or manager."""
    if current_user.role not in ("club_owner", "club_manager", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club staff can access this endpoint",
        )

    membership = await _get_any_membership(db, current_user.id)

    result = await db.execute(
        select(Court)
        .where(Court.club_id == membership.club_id, Court.is_active == True)
        .order_by(Court.name)
    )
    courts = result.scalars().all()

    return [
        CourtOut(
            id=c.id,
            name=c.name,
            sport_id=c.sport_id,
            surface=c.surface,
            is_indoor=c.is_indoor,
            price_per_hour=float(c.price_per_hour),
            currency=c.currency,
        )
        for c in courts
    ]


@router.get("/my/bookings", response_model=list[dict])
async def list_my_club_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List bookings for the caller's club. Owner or manager."""
    if current_user.role not in ("club_owner", "club_manager", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club staff can access this endpoint",
        )

    membership = await _get_any_membership(db, current_user.id)

    result = await db.execute(
        select(Booking)
        .join(Booking.slot)
        .join(CourtSlot.court)
        .where(Court.club_id == membership.club_id)
        .options(
            selectinload(Booking.slot).selectinload(CourtSlot.court),
        )
        .order_by(Booking.created_at.desc())
    )
    bookings = result.scalars().all()

    return [
        {
            "booking_id": str(b.id),
            "booked_by": str(b.booked_by),
            "booking_status": b.status,
            "payment_status": b.payment_status,
            "court_id": str(b.slot.court_id),
            "court_name": b.slot.court.name,
            "slot_date": b.slot.slot_date.isoformat(),
            "start_time": b.slot.start_time.isoformat(),
            "end_time": b.slot.end_time.isoformat(),
            "created_at": b.created_at.isoformat(),
        }
        for b in bookings
    ]


@router.get("/my/members", response_model=list[dict])
async def list_my_club_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all ClubMember records for the caller's club. Owner only."""
    if current_user.role not in ("club_owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club owners can view member list",
        )

    membership = await _get_owner_membership(db, current_user.id)

    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.club_id == membership.club_id)
        .options(selectinload(ClubMember.user).selectinload(User.profile))
        .order_by(ClubMember.created_at)
    )
    members = result.scalars().all()

    return [
        {
            "member_id": str(m.id),
            "user_id": str(m.user_id),
            "role": m.role,
            "email": m.user.email,
            "display_name": m.user.profile.display_name if m.user.profile else "",
            "joined_at": m.created_at.isoformat(),
        }
        for m in members
    ]


# ---------------------------------------------------------------------------
# Public endpoints — after /my/* to avoid /{slug} matching "my"
# ---------------------------------------------------------------------------


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
