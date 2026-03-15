import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class CreateInviteRequest(BaseModel):
    invite_type: Literal["club_owner", "club_manager"]
    club_id: uuid.UUID | None = None
    email_hint: EmailStr | None = None
    expires_in_hours: int = Field(default=72, ge=1, le=720)  # 1 hour – 30 days


class InviteOut(BaseModel):
    id: uuid.UUID
    invite_type: str
    club_id: uuid.UUID | None
    club_name: str | None
    email_hint: str | None
    expires_at: datetime
    is_active: bool
    claimed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteWithTokenOut(InviteOut):
    raw_token: str


class InviteValidationOut(BaseModel):
    valid: bool
    invite_type: str | None = None
    club_name: str | None = None
    email_hint: str | None = None
    error: str | None = None  # "expired", "already_claimed", "not_found", "inactive"


class RegisterWithInviteRequest(BaseModel):
    token: str
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)


class ClaimInviteRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class CreateManagerInviteRequest(BaseModel):
    email_hint: EmailStr | None = None
    expires_in_hours: int = Field(default=168, ge=1, le=720)  # default 1 week, max 30 days


class ClubSetupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=300)
    city: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    description: str | None = None


class AddCourtRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sport_id: uuid.UUID
    price_per_hour: float = Field(ge=0)
    surface: str | None = None
    is_indoor: bool = True
    currency: str = Field(default="KZT", max_length=3)


class MyClubOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    address: str | None
    city: str | None
    phone: str | None
    description: str | None
    is_verified: bool
    member_role: str  # "owner" or "manager"

    model_config = {"from_attributes": True}
