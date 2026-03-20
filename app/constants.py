"""Shared status enums used across routers, models, and schemas.

Using StrEnum so values serialize as plain strings — fully compatible
with SQLAlchemy column defaults, Pydantic schemas, and JSON responses.
"""

from enum import StrEnum


class SlotStatus(StrEnum):
    AVAILABLE = "available"
    BOOKED = "booked"
    BLOCKED = "blocked"


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"


class RefundStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    COMPLETED = "completed"


class MatchStatus(StrEnum):
    OPEN = "open"
    FULL = "full"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class PlayerStatus(StrEnum):
    INVITED = "invited"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class ResultSource(StrEnum):
    MANUAL = "manual"
    CONSENSUS = "consensus"
    AI_CAMERA = "ai_camera"


class ResultConfirmation(StrEnum):
    """Status returned by the submit-result endpoint."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
