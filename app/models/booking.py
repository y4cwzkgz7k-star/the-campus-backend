import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("court_slots.id"), nullable=False, index=True)
    booked_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "confirmed", "cancelled", "completed", "no_show", name="booking_status"),
        default="confirmed",
        nullable=False,
    )
    # Payment placeholder — will be populated when payment provider is integrated
    payment_status: Mapped[str] = mapped_column(
        Enum("pending", "paid", "refunded", "failed", name="payment_status"),
        default="pending",
        nullable=False,
    )
    payment_provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)

    slot: Mapped["CourtSlot"] = relationship()
    user: Mapped["User"] = relationship()
