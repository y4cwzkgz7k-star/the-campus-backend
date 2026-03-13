from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import User, UserProfile
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserInToken

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_to_token_user(user: User) -> UserInToken:
    return UserInToken(
        id=str(user.id),
        email=user.email,
        phone=user.phone,
        display_name=user.profile.display_name if user.profile else "",
        avatar_url=user.profile.avatar_url if user.profile else None,
        city=user.profile.city if user.profile else None,
        role=user.role,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        phone=body.phone,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    profile = UserProfile(user_id=user.id, display_name=body.display_name)
    db.add(profile)
    await db.commit()

    result = await db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.profile))
    )
    user = result.scalar_one()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_to_token_user(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email).options(selectinload(User.profile))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_to_token_user(user),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(
        select(User).where(User.id == payload["sub"]).options(selectinload(User.profile))
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_to_token_user(user),
    )
