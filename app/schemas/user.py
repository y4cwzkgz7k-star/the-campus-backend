import uuid
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class SportLevel(BaseModel):
    sport_id: uuid.UUID
    level: str


class OnboardingRequest(BaseModel):
    # Restricted to allowed roles — prevents privilege escalation via onboarding
    role: Literal["player", "trainer"]
    # Cap sports list to prevent unbounded DB inserts
    sports: Annotated[list[SportLevel], Field(max_length=20)]
    city: str
    latitude: float | None = None
    longitude: float | None = None


class UserSportOut(BaseModel):
    sport_id: uuid.UUID
    sport_slug: str
    sport_name: str
    level: str

    model_config = {"from_attributes": True}


class UserProfileOut(BaseModel):
    display_name: str
    avatar_url: str | None
    bio: str | None
    city: str | None
    onboarding_completed: bool
    reliability_score: float = 100.0
    total_bookings: int = 0
    cancelled_bookings: int = 0

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_verified: bool
    profile: UserProfileOut | None
    sports: list[UserSportOut]

    model_config = {"from_attributes": True}


# Flat representation used by frontend auth context
class UserFlatOut(BaseModel):
    id: uuid.UUID
    email: str
    phone: str | None
    display_name: str
    avatar_url: str | None
    city: str | None
    role: str
    sports: list[UserSportOut]
    reliability_score: float = 100.0
    rating: float = 1200.0


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    # Only allow https:// URLs to prevent XSS/SSRF via javascript: or data: schemes
    avatar_url: str | None = Field(default=None, pattern=r'^https?://.+', max_length=500)


class UserSearchResult(BaseModel):
    id: uuid.UUID
    display_name: str
    avatar_url: str | None
    city: str | None
    sports: list[UserSportOut]
    reliability_score: float = 100.0

    model_config = {"from_attributes": True}
