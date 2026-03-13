import uuid
from pydantic import BaseModel


class SportLevel(BaseModel):
    sport_id: uuid.UUID
    level: str


class OnboardingRequest(BaseModel):
    role: str
    sports: list[SportLevel]
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
    display_name: str | None = None
    bio: str | None = None
    city: str | None = None
    avatar_url: str | None = None


class UserSearchResult(BaseModel):
    id: uuid.UUID
    display_name: str
    avatar_url: str | None
    city: str | None
    sports: list[UserSportOut]
    reliability_score: float = 100.0

    model_config = {"from_attributes": True}
