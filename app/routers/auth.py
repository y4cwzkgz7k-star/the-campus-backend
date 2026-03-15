from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.limiter import limiter
from app.utils.token import hash_token
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.club import Club
from app.models.club_member import ClubMember
from app.models.invite_token import InviteToken
from app.models.user import User, UserProfile
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserInToken,
)
from app.schemas.invite import RegisterWithInviteRequest
from app.services.email_service import (
    generate_token,
    send_password_reset_email,
    send_verification_email,
    verify_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_RESET_TOKEN_TTL = timedelta(hours=1)


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

    raw_token, token_hash = generate_token()

    user = User(
        email=body.email,
        phone=body.phone,
        hashed_password=hash_password(body.password),
        email_verification_token_hash=token_hash,
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

    send_verification_email(user.email, user.profile.display_name, raw_token)

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_to_token_user(user),
    )


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_email(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email_verification_token_hash.isnot(None))
    )
    # We can't query by raw token, so we load candidates and check hash
    # (token column is indexed by hash — look up directly)
    from app.services.email_service import _token_hash
    token_hash = _token_hash(token)

    result = await db.execute(
        select(User).where(User.email_verification_token_hash == token_hash)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    if user.is_verified:
        return {"detail": "Email already verified"}

    user.is_verified = True
    user.email_verification_token_hash = None
    await db.commit()

    return {"detail": "Email verified successfully"}


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def resend_verification(request: Request, email: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == email).options(selectinload(User.profile))
    )
    user = result.scalar_one_or_none()

    # Always return 200 to avoid email enumeration
    if not user or user.is_verified:
        return {"detail": "If that email is registered and unverified, a new link has been sent"}

    raw_token, token_hash = generate_token()
    user.email_verification_token_hash = token_hash
    await db.commit()

    send_verification_email(user.email, user.profile.display_name if user.profile else "", raw_token)

    return {"detail": "If that email is registered and unverified, a new link has been sent"}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email).options(selectinload(User.profile))
    )
    user = result.scalar_one_or_none()

    # Always return 200 to avoid email enumeration
    if user and user.is_active:
        raw_token, token_hash = generate_token()
        user.password_reset_token_hash = token_hash
        user.password_reset_expires_at = datetime.now(timezone.utc) + _RESET_TOKEN_TTL
        await db.commit()
        send_password_reset_email(user.email, user.profile.display_name if user.profile else "", raw_token)

    return {"detail": "If that email is registered, a reset link has been sent"}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def reset_password(request: Request, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    from app.services.email_service import _token_hash
    token_hash = _token_hash(body.token)

    result = await db.execute(
        select(User).where(User.password_reset_token_hash == token_hash)
    )
    user = result.scalar_one_or_none()

    if not user or not user.password_reset_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if datetime.now(timezone.utc) > user.password_reset_expires_at:
        raise HTTPException(status_code=400, detail="Reset link has expired")

    user.hashed_password = hash_password(body.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    await db.commit()

    return {"detail": "Password updated successfully"}


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


@router.post(
    "/register-with-invite",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/minute")
async def register_with_invite(
    request: Request,
    body: RegisterWithInviteRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # 1. Look up invite by token hash
    token_hash = hash_token(body.token)
    invite_result = await db.execute(
        select(InviteToken)
        .where(InviteToken.token_hash == token_hash)
        .options(selectinload(InviteToken.club))
    )
    invite = invite_result.scalar_one_or_none()

    if invite is None:
        raise HTTPException(status_code=400, detail="Invalid invite token")
    if not invite.is_active:
        raise HTTPException(status_code=400, detail="Invite is no longer active")
    if invite.claimed_at is not None:
        raise HTTPException(status_code=400, detail="Invite has already been claimed")
    if datetime.now(timezone.utc) > invite.expires_at:
        raise HTTPException(status_code=400, detail="Invite has expired")

    # 2. Validate email not taken
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 3. Create user with role from invite
    user = User(
        email=body.email,
        phone=body.phone,
        hashed_password=hash_password(body.password),
        role=invite.invite_type,  # "club_owner" or "club_manager"
        is_verified=True,  # Invite acts as email verification
    )
    db.add(user)
    await db.flush()

    # 4. Create user profile
    profile = UserProfile(user_id=user.id, display_name=body.display_name)
    db.add(profile)
    await db.flush()

    # 5. Create club membership if invite has a club_id
    if invite.club_id is not None:
        member_role = "owner" if invite.invite_type == "club_owner" else "manager"
        membership = ClubMember(
            club_id=invite.club_id,
            user_id=user.id,
            role=member_role,
        )
        db.add(membership)
        await db.flush()

        # 6. If club_owner invite — update Club.owner_user_id
        if invite.invite_type == "club_owner":
            club_result = await db.execute(
                select(Club).where(Club.id == invite.club_id)
            )
            club = club_result.scalar_one_or_none()
            if club is not None:
                club.owner_user_id = user.id

    # 7. Mark invite claimed and deactivate
    invite.claimed_by_user_id = user.id
    invite.claimed_at = datetime.now(timezone.utc)
    invite.is_active = False

    # 8. Commit atomically
    await db.commit()

    # 9. Reload user with profile for token response
    reloaded = await db.execute(
        select(User).where(User.id == user.id).options(selectinload(User.profile))
    )
    user = reloaded.scalar_one()

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=_user_to_token_user(user),
    )
