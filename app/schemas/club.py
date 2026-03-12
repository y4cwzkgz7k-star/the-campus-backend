import uuid
from datetime import date, time
from pydantic import BaseModel


class CourtOut(BaseModel):
    id: uuid.UUID
    name: str
    sport_id: uuid.UUID
    surface: str | None
    is_indoor: bool
    price_per_hour: float
    currency: str

    model_config = {"from_attributes": True}


class ClubOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    address: str | None
    city: str | None
    latitude: float | None
    longitude: float | None
    description: str | None
    phone: str | None
    is_verified: bool
    courts: list[CourtOut] = []

    model_config = {"from_attributes": True}


class SlotOut(BaseModel):
    id: uuid.UUID
    court_id: uuid.UUID
    slot_date: date
    start_time: time
    end_time: time
    status: str
    price: float

    model_config = {"from_attributes": True}
