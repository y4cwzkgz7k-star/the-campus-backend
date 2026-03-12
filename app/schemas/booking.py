import uuid
from datetime import datetime
from pydantic import BaseModel


class CreateBookingRequest(BaseModel):
    slot_id: uuid.UUID
    notes: str | None = None


class BookingOut(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    status: str
    payment_status: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
