import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.limiter import limiter
from app.database import get_db
from app.deps import get_current_user
from app.models.club import Club
from app.models.club_member import ClubMember
from app.models.invite_token import InviteToken
from app.models.user import User
from app.schemas.invite import (
    ClaimInviteRequest,
    CreateInviteRequest,
    CreateManagerInviteRequest,
    InviteOut,
    InviteValidationOut,
    InviteWithTokenOut,
)
from app.utils.token import hash_token

router = APIRouter(prefix="/invites", tags=["invites"])

_MAX_EXPIRES_HOURS = 24 * 30  # 30 days hard cap


def _generate_raw_token() -> tuple[str, str]:
    """Return (raw_token, token_hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def _invite_to_out(invite: InviteToken) -> InviteOut:
    return InviteOut(
        id=invite.id,
        invite_type=invite.invite_type,
        club_id=invite.club_id,
        club_name=invite.club.name if invite.club else None,
        email_hint=invite.email_hint,
        expires_at=invite.expires_at,
        is_active=invite.is_active,
        claimed_at=invite.claimed_at,
        created_at=invite.created_at,
    )


def _invite_to_out_with_token(invite: InviteToken, raw_token: str) -> InviteWithTokenOut:
    return InviteWithTokenOut(
        id=invite.id,
        invite_type=invite.invite_type,
        club_id=invite.club_id,
        club_name=invite.club.name if invite.club else None,
        email_hint=invite.email_hint,
        expires_at=invite.expires_at,
        is_active=invite.is_active,
        claimed_at=invite.claimed_at,
        created_at=invite.created_at,
        raw_token=raw_token,
    )


def _require_admin(current_user: User) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


async def _require_club_owner_membership(
    db: AsyncSession, user_id: uuid.UUID
) -> ClubMember:
    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.user_id == user_id, ClubMember.role == "owner")
        .options(selectinload(ClubMember.club))
        .limit(1)
    )
    membership = result.scalars().first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a club owner to perform this action",
        )
    return membership


async def _load_invite_by_hash(
    db: AsyncSession, token_hash: str, for_update: bool = False
) -> InviteToken | None:
    q = (
        select(InviteToken)
        .where(InviteToken.token_hash == token_hash)
        .options(selectinload(InviteToken.club))
    )
    if for_update:
        q = q.with_for_update()
    result = await db.execute(q)
    return result.scalar_one_or_none()


def _validate_invite_state(invite: InviteToken | None) -> InviteValidationOut:
    """Return InviteValidationOut for any token state without raising."""
    if invite is None:
        return InviteValidationOut(valid=False, error="not_found")

    if not invite.is_active:
        return InviteValidationOut(valid=False, error="inactive")

    if invite.claimed_at is not None:
        return InviteValidationOut(valid=False, error="already_claimed")

    now = datetime.now(timezone.utc)
    if now > invite.expires_at:
        return InviteValidationOut(valid=False, error="expired")

    return InviteValidationOut(
        valid=True,
        invite_type=invite.invite_type,
        club_name=invite.club.name if invite.club else None,
        email_hint=invite.email_hint,
    )


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@router.get("/validate", response_model=InviteValidationOut)
@limiter.limit("30/minute")
async def validate_invite(
    request: Request,
    token: str = Query(..., min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
) -> InviteValidationOut:
    token_hash = hash_token(token)
    invite = await _load_invite_by_hash(db, token_hash)
    return _validate_invite_state(invite)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.post("/", response_model=InviteWithTokenOut, status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: CreateInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteWithTokenOut:
    _require_admin(current_user)

    expires_in = min(body.expires_in_hours, _MAX_EXPIRES_HOURS)
    raw, token_hash = _generate_raw_token()

    invite = InviteToken(
        token_hash=token_hash,
        invite_type=body.invite_type,
        club_id=body.club_id,
        created_by_user_id=current_user.id,
        email_hint=body.email_hint,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in),
    )
    db.add(invite)
    await db.flush()

    # Reload with club relationship populated
    invite = await _load_invite_by_hash(db, token_hash)
    await db.commit()

    return _invite_to_out_with_token(invite, raw)


@router.get("/", response_model=list[InviteOut])
async def list_invites(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InviteOut]:
    _require_admin(current_user)

    result = await db.execute(
        select(InviteToken)
        .options(selectinload(InviteToken.club))
        .order_by(InviteToken.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    invites = result.scalars().all()
    return [_invite_to_out(i) for i in invites]


@router.delete("/{invite_id}", status_code=status.HTTP_200_OK)
async def deactivate_invite(
    invite_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(current_user)

    result = await db.execute(
        select(InviteToken).where(InviteToken.id == invite_id)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    if not invite.is_active:
        return {"detail": "Invite is already inactive"}

    invite.is_active = False
    await db.commit()
    return {"detail": "Invite deactivated"}


# ---------------------------------------------------------------------------
# Club owner endpoints
# ---------------------------------------------------------------------------


@router.post("/manager", response_model=InviteWithTokenOut, status_code=status.HTTP_201_CREATED)
async def create_manager_invite(
    body: CreateManagerInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteWithTokenOut:
    if current_user.role != "club_owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only club owners can create manager invites",
        )

    membership = await _require_club_owner_membership(db, current_user.id)

    expires_in = min(body.expires_in_hours, _MAX_EXPIRES_HOURS)
    raw, token_hash = _generate_raw_token()

    invite = InviteToken(
        token_hash=token_hash,
        invite_type="club_manager",
        club_id=membership.club_id,
        created_by_user_id=current_user.id,
        email_hint=body.email_hint,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in),
    )
    db.add(invite)
    await db.flush()

    invite = await _load_invite_by_hash(db, token_hash)
    await db.commit()

    return _invite_to_out_with_token(invite, raw)


# ---------------------------------------------------------------------------
# Authenticated user — claim invite
# ---------------------------------------------------------------------------


@router.post("/claim", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def claim_invite(
    request: Request,
    body: ClaimInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token_hash = hash_token(body.token)

    # SELECT FOR UPDATE prevents TOCTOU race: two simultaneous claims of the same token
    invite = await _load_invite_by_hash(db, token_hash, for_update=True)

    validation = _validate_invite_state(invite)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=validation.error or "Invalid invite",
        )

    if invite.invite_type not in ("club_owner", "club_manager"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only club_owner or club_manager invites can be claimed by existing users",
        )

    # For club_manager invites a club must already exist
    if invite.invite_type == "club_manager" and invite.club_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager invite is not linked to a club",
        )

    # Check for duplicate membership (only relevant when club_id is set)
    if invite.club_id is not None:
        existing_result = await db.execute(
            select(ClubMember).where(
                ClubMember.club_id == invite.club_id,
                ClubMember.user_id == current_user.id,
            )
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already a member of this club",
            )

    # Update user role to match the invite type
    current_user.role = invite.invite_type  # "club_owner" or "club_manager"

    # Create club membership when a club is already linked
    if invite.club_id is not None:
        member_role = "owner" if invite.invite_type == "club_owner" else "manager"
        membership = ClubMember(
            club_id=invite.club_id,
            user_id=current_user.id,
            role=member_role,
        )
        db.add(membership)

    # Mark invite claimed and deactivate so admin UI shows correct state
    invite.claimed_by_user_id = current_user.id
    invite.claimed_at = datetime.now(timezone.utc)
    invite.is_active = False

    await db.commit()
    return {
        "detail": "Invite claimed successfully",
        "invite_type": invite.invite_type,
        "club_id": str(invite.club_id) if invite.club_id else None,
    }
