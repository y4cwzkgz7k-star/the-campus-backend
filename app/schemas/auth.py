import uuid
from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    phone: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class UserInToken(BaseModel):
    id: str
    email: str
    phone: str | None
    display_name: str
    avatar_url: str | None
    city: str | None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInToken | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
