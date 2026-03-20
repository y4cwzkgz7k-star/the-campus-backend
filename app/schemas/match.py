import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class CreateMatchRequest(BaseModel):
    sport_id: uuid.UUID
    title: str | None = Field(default=None, max_length=150)
    format: str = "doubles"
    max_players: int = 4
    scheduled_at: datetime | None = None
    notes: str | None = None
    city: str | None = None
    booking_id: uuid.UUID | None = None


class MatchPlayerOut(BaseModel):
    id: uuid.UUID          # = user_id, named id so frontend can use player.id uniformly
    display_name: str
    avatar_url: str | None
    status: str
    rating: float | None = None

    model_config = {"from_attributes": True}


class MatchOut(BaseModel):
    id: uuid.UUID
    sport_id: uuid.UUID
    title: str | None = None
    format: str
    status: str
    max_players: int
    current_players: int = 0
    created_by: uuid.UUID | None = None
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


class SubmitResultResponse(BaseModel):
    """Unified response for the two-confirmation result flow.

    Possible statuses:
      - "pending"   : first submission recorded, waiting for opponent
      - "confirmed" : both players agreed, ELO updated
      - "disputed"  : scores do not match, needs resolution
    """
    status: str
    message: str
    match: MatchOut
    # Only present when status == "confirmed"
    player_a: PlayerEloOut | None = None
    player_b: PlayerEloOut | None = None
