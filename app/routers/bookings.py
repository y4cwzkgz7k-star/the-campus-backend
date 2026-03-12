from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.booking import Booking
from app.models.court import CourtSlot
from app.models.user import User
from app.schemas.booking import BookingOut, CreateBookingRequest

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingOut, status_code=201)
async def create_booking(
    body: CreateBookingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Lock slot to prevent race condition
    result = await db.execute(
        select(CourtSlot)
        .where(CourtSlot.id == body.slot_id)
        .with_for_update()
    )
    slot = result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.status != "available":
        raise HTTPException(status_code=409, detail="Slot is no longer available")

    slot.status = "booked"
    booking = Booking(
        slot_id=slot.id,
        booked_by=current_user.id,
        notes=body.notes,
        # payment_status stays "pending" until payment provider is integrated
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


@router.get("/me", response_model=list[BookingOut])
async def my_bookings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Booking)
        .where(Booking.booked_by == current_user.id)
        .order_by(Booking.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.delete("/{booking_id}", status_code=204)
async def cancel_booking(
    booking_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.booked_by == current_user.id,
        )
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status in ("cancelled", "completed"):
        raise HTTPException(status_code=400, detail="Cannot cancel this booking")

    booking.status = "cancelled"
    slot_result = await db.execute(select(CourtSlot).where(CourtSlot.id == booking.slot_id))
    slot = slot_result.scalar_one_or_none()
    if slot:
        slot.status = "available"

    await db.commit()
