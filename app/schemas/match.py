import uuid
from datetime import datetime
from pydantic import BaseModel, Field


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
    score_home: int | None = None
    score_away: int | None = None
    # Tells the frontend how trustworthy the result is:
    # "manual" = player-reported, "consensus" = both agreed, "ai_camera" = verified by court AI
    result_source: str = "manual"
    players: list[MatchPlayerOut] = []

    model_config = {"from_attributes": True}


class MatchResultRequest(BaseModel):
    score_home: int = Field(..., ge=0)
    score_away: int = Field(..., ge=0)


class PlayerEloOut(BaseModel):
    user_id: uuid.UUID
    new_rating: float


class MatchResultOut(BaseModel):
    match: MatchOut
    player_a: PlayerEloOut
    player_b: PlayerEloOut
