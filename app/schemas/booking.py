import uuid
from datetime import datetime
from pydantic import BaseModel


class CreateBookingRequest(BaseModel):
    slot_id: uuid.UUID
    notes: str | None = None


class CancelBookingRequest(BaseModel):
    reason: str | None = None


class BookingOut(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    status: str
    payment_status: str
    notes: str | None
    created_at: datetime
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None
    refund_status: str = "none"
    client_secret: str | None = None

    model_config = {"from_attributes": True}
