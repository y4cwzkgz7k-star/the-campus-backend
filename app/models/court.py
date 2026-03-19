import uuid
from datetime import date, time

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Court(Base):
    __tablename__ = "courts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    sport_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sports.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    surface: Mapped[str | None] = mapped_column(
        Enum("synthetic", "hard", "clay", "grass", "parquet", name="court_surface"),
        nullable=True,
    )
    is_indoor: Mapped[bool] = mapped_column(Boolean, default=True)
    price_per_hour: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    club: Mapped["Club"] = relationship(back_populates="courts")
    sport: Mapped["Sport"] = relationship()
    slots: Mapped[list["CourtSlot"]] = relationship(back_populates="court", cascade="all, delete-orphan")


class CourtSlot(Base):
    __tablename__ = "court_slots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    court_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courts.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("available", "booked", "blocked", name="slot_status"),
        default="available",
        nullable=False,
    )
    price_override: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    court: Mapped["Court"] = relationship(back_populates="slots")
