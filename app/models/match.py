import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sport_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sports.id"), nullable=False, index=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    format: Mapped[str] = mapped_column(
        Enum("singles", "doubles", "group", name="match_format"),
        default="doubles",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum("open", "full", "in_progress", "completed", "cancelled", "disputed", name="match_status"),
        default="open",
        nullable=False,
    )
    max_players: Mapped[int] = mapped_column(Integer, default=4)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    score_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Hook for AI camera integration (Phase 3).
    # "manual"     — result submitted by a player (current default, manipulation-prone)
    # "consensus"  — both players submitted matching scores (Phase 2)
    # "ai_camera"  — result delivered by court AI system (e.g. SportAI webhook) — fully trusted
    result_source: Mapped[str] = mapped_column(
        Enum("manual", "consensus", "ai_camera", name="result_source", create_type=False),
        nullable=False,
        default="manual",       # Python-level default (prevents NULL on flush)
        server_default="manual",  # DB-level default (for raw SQL inserts)
    )

    # --- Two-confirmation result consensus fields (Phase 2) ---
    # Tracks the first player who submitted a pending result.
    # NULL means no pending result yet.
    result_submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    submitted_score_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_score_away: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sport: Mapped["Sport"] = relationship()
    booking: Mapped["Booking"] = relationship()
    players: Mapped[list["MatchPlayer"]] = relationship(back_populates="match", cascade="all, delete-orphan")


class MatchPlayer(Base):
    __tablename__ = "match_players"

    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    status: Mapped[str] = mapped_column(
        Enum("invited", "confirmed", "declined", name="player_status"),
        default="confirmed",
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    match: Mapped["Match"] = relationship(back_populates="players")
    user: Mapped["User"] = relationship()
