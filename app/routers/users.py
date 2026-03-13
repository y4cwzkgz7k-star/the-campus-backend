import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User, UserProfile, UserSport
from app.models.sport import Sport
from app.schemas.user import (
    OnboardingRequest,
    UpdateProfileRequest,
    UserFlatOut,
    UserOut,
    UserSearchResult,
    UserSportOut,
)

router = APIRouter(prefix="/users", tags=["users"])


def _build_user_flat(user: User) -> UserFlatOut:
    sports = [
        UserSportOut(
            sport_id=us.sport_id,
            sport_slug=us.sport.slug,
            sport_name=us.sport.name,
            level=us.level,
        )
        for us in (user.sports or [])
        if us.sport
    ]
    return UserFlatOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        display_name=user.profile.display_name if user.profile else "",
        avatar_url=user.profile.avatar_url if user.profile else None,
        city=user.profile.city if user.profile else None,
        role=user.role,
        sports=sports,
        reliability_score=user.profile.reliability_score if user.profile else 100.0,
        rating=user.profile.rating if user.profile else 1200.0,
    )


def _build_user_out(user: User) -> UserOut:
    sports = [
        UserSportOut(
            sport_id=us.sport_id,
            sport_slug=us.sport.slug,
            sport_name=us.sport.name,
            level=us.level,
        )
        for us in (user.sports or [])
        if us.sport
    ]
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_verified=user.is_verified,
        profile=user.profile,
        sports=sports,
    )


@router.get("/me", response_model=UserFlatOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return _build_user_flat(current_user)


@router.put("/me", response_model=UserFlatOut)
async def update_me(
    body: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = current_user.profile
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if body.display_name is not None:
        profile.display_name = body.display_name
    if body.bio is not None:
        profile.bio = body.bio
    if body.city is not None:
        profile.city = body.city
    if body.avatar_url is not None:
        profile.avatar_url = body.avatar_url

    await db.commit()
    await db.refresh(current_user)
    return _build_user_flat(current_user)


@router.post("/me/onboarding", response_model=UserOut)
async def complete_onboarding(
    body: OnboardingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.role = body.role

    profile = current_user.profile
    profile.city = body.city
    profile.latitude = body.latitude
    profile.longitude = body.longitude
    profile.onboarding_completed = True

    # Replace sports
    await db.execute(
        UserSport.__table__.delete().where(UserSport.user_id == current_user.id)
    )
    for s in body.sports:
        db.add(UserSport(user_id=current_user.id, sport_id=s.sport_id, level=s.level))

    await db.commit()

    result = await db.execute(
        select(User)
        .where(User.id == current_user.id)
        .options(selectinload(User.profile), selectinload(User.sports).selectinload(UserSport.sport))
    )
    user = result.scalar_one()
    return _build_user_out(user)


@router.get("/{user_id}", response_model=UserSearchResult)
async def get_public_profile(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .where(User.id == user_id, User.is_active == True)
        .options(selectinload(User.profile), selectinload(User.sports).selectinload(UserSport.sport))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sports = [
        UserSportOut(
            sport_id=us.sport_id,
            sport_slug=us.sport.slug,
            sport_name=us.sport.name,
            level=us.level,
        )
        for us in user.sports
        if us.sport
    ]
    return UserSearchResult(
        id=user.id,
        display_name=user.profile.display_name if user.profile else "",
        avatar_url=user.profile.avatar_url if user.profile else None,
        city=user.profile.city if user.profile else None,
        sports=sports,
        reliability_score=user.profile.reliability_score if user.profile else 100.0,
    )


@router.get("/", response_model=list[UserSearchResult])
async def search_users(
    sport_slug: str | None = None,
    level: str | None = None,
    city: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = (
        select(User)
        .where(User.is_active == True)
        .options(
            selectinload(User.profile),
            selectinload(User.sports).selectinload(UserSport.sport),
        )
        .join(User.profile)
    )

    if city:
        safe_city = city.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(UserProfile.city.ilike(f"%{safe_city}%", escape="\\"))

    if sport_slug or level:
        query = query.join(User.sports).join(UserSport.sport)
        if sport_slug:
            query = query.where(Sport.slug == sport_slug)
        if level:
            query = query.where(UserSport.level == level)

    result = await db.execute(query.limit(50))
    users = result.scalars().unique().all()

    out = []
    for u in users:
        sports = [
            UserSportOut(
                sport_id=us.sport_id,
                sport_slug=us.sport.slug,
                sport_name=us.sport.name,
                level=us.level,
            )
            for us in u.sports
            if us.sport
        ]
        out.append(UserSearchResult(
            id=u.id,
            display_name=u.profile.display_name if u.profile else "",
            avatar_url=u.profile.avatar_url if u.profile else None,
            city=u.profile.city if u.profile else None,
            sports=sports,
            reliability_score=u.profile.reliability_score if u.profile else 100.0,
        ))
    return out
