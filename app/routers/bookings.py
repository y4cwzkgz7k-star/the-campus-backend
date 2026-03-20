import os
import uuid
from datetime import datetime, timezone, timedelta, date, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.booking import Booking
from app.models.court import CourtSlot
from app.models.user import User, UserProfile
from app.schemas.booking import BookingOut, CancelBookingRequest, CreateBookingRequest

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Refund window: bookings cancelled at least this many hours before slot start get a refund
REFUND_CUTOFF_HOURS = 2


def _slot_start_utc(slot: CourtSlot) -> datetime:
    """Combine slot_date + start_time into a UTC-aware datetime."""
    naive = datetime.combine(slot.slot_date, slot.start_time)
    return naive.replace(tzinfo=timezone.utc)


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

    # Update user profile booking count
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id).with_for_update()
    )
    profile = profile_result.scalar_one_or_none()
    if profile is not None:
        profile.total_bookings = profile.total_bookings + 1

    # Stripe integration — call BEFORE commit to ensure atomicity.
    # If Stripe fails, we roll back everything (slot stays available, no orphaned booking).
    client_secret: str | None = None
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if stripe_key:
        import stripe  # type: ignore

        amount_cents = int((float(slot.price_override or 0)) * 100)
        if amount_cents > 0:
            try:
                client = stripe.StripeClient(stripe_key)
                intent = client.payment_intents.create(
                    params={
                        "amount": amount_cents,
                        "currency": "kzt",
                        "metadata": {"booking_id": str(booking.id), "user_id": str(current_user.id)},
                    }
                )
                client_secret = intent.client_secret
                booking.payment_provider_id = intent.id
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Stripe PaymentIntent failed: %s", e)
                await db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail="Payment provider error — please try again",
                )

    # Single atomic commit: booking + slot status + payment_provider_id
    await db.commit()
    await db.refresh(booking)

    # Build response manually to inject client_secret (not a DB column)
    return BookingOut(
        id=booking.id,
        slot_id=booking.slot_id,
        status=booking.status,
        payment_status=booking.payment_status,
        notes=booking.notes,
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
        cancellation_reason=booking.cancellation_reason,
        refund_status=booking.refund_status,
        client_secret=client_secret,
    )


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


@router.patch("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: uuid.UUID,
    body: CancelBookingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Load booking with lock
    booking_result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .with_for_update()
    )
    booking = booking_result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Only the owner can cancel
    if booking.booked_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the booking owner can cancel")

    if booking.status in ("cancelled", "completed"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel a booking with status '{booking.status}'")

    # Load slot to determine time until start and to free it
    slot_result = await db.execute(
        select(CourtSlot)
        .where(CourtSlot.id == booking.slot_id)
        .with_for_update()
    )
    slot = slot_result.scalar_one_or_none()

    now_utc = datetime.now(timezone.utc)
    refund_status = "none"

    if slot is not None:
        slot_start = _slot_start_utc(slot)
        hours_until_start = (slot_start - now_utc).total_seconds() / 3600.0
        refund_status = "pending" if hours_until_start >= REFUND_CUTOFF_HOURS else "none"
        slot.status = "available"

    # Load profile with lock to update reliability score
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id).with_for_update()
    )
    profile = profile_result.scalar_one_or_none()

    new_cancelled = (profile.cancelled_bookings if profile else 0) + 1
    new_total = (profile.total_bookings if profile else 1)
    new_reliability = max(0.0, (1.0 - new_cancelled / max(new_total, 1)) * 100.0)

    if profile is not None:
        profile.cancelled_bookings = new_cancelled
        profile.reliability_score = round(new_reliability, 2)

    # Update booking fields
    booking.status = "cancelled"
    booking.cancelled_at = now_utc
    booking.cancellation_reason = body.reason
    booking.refund_status = refund_status

    await db.commit()
    await db.refresh(booking)
    return booking


# DELETE /bookings/{id} removed — use PATCH /bookings/{id}/cancel instead.
# The DELETE path bypassed refund logic, reliability score updates, and row locking.
