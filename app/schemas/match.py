import uuid
from datetime import datetime
from pydantic import BaseModel


class CreateMatchRequest(BaseModel):
    sport_id: uuid.UUID
    format: str = "doubles"
    max_players: int = 4
    scheduled_at: datetime | None = None
    notes: str | None = None
    city: str | None = None
    booking_id: uuid.UUID | None = None


class MatchPlayerOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    avatar_url: str | None
    status: str

    model_config = {"from_attributes": True}


class MatchOut(BaseModel):
    id: uuid.UUID
    sport_id: uuid.UUID
    format: str
    status: str
    max_players: int
    scheduled_at: datetime | None
    notes: str | None
    city: str | None
    created_at: datetime
    players: list[MatchPlayerOut] = []

    model_config = {"from_attributes": True}
