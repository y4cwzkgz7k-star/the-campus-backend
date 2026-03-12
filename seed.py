"""
Seed script — populates sports and demo data.
Run: python seed.py
"""
import asyncio
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.sport import Sport
from app.models.user import User, UserProfile, UserSport
from app.models.club import Club
from app.models.court import Court, CourtSlot
from datetime import date, time, timedelta

SPORTS = [
    {"slug": "padel", "name": "Падел", "icon": "🎾"},
    {"slug": "tennis", "name": "Теннис", "icon": "🎾"},
    {"slug": "basketball", "name": "Баскетбол", "icon": "🏀"},
    {"slug": "volleyball", "name": "Волейбол", "icon": "🏐"},
    {"slug": "pickleball", "name": "Пиклбол", "icon": "🏓"},
    {"slug": "fitness", "name": "Фитнес", "icon": "💪"},
    {"slug": "running", "name": "Бег", "icon": "🏃"},
]


async def seed():
    async with AsyncSessionLocal() as db:
        # Sports
        sport_map = {}
        for s in SPORTS:
            existing = await db.execute(select(Sport).where(Sport.slug == s["slug"]))
            if not existing.scalar_one_or_none():
                sport = Sport(**s)
                db.add(sport)
                await db.flush()
                sport_map[s["slug"]] = sport.id
            else:
                sport_map[s["slug"]] = existing.scalar_one().id

        # Demo club
        club_result = await db.execute(select(Club).where(Club.slug == "campus-almaty"))
        if not club_result.scalar_one_or_none():
            club = Club(
                name="Campus Club Almaty",
                slug="campus-almaty",
                city="Алматы",
                address="ул. Абая 1, Алматы",
                latitude=43.238949,
                longitude=76.945465,
                description="Первый клуб платформы The Campus",
                is_verified=True,
            )
            db.add(club)
            await db.flush()

            # Padel court
            court = Court(
                club_id=club.id,
                sport_id=sport_map["padel"],
                name="Корт 1",
                surface="synthetic",
                is_indoor=True,
                price_per_hour=5000,
                currency="KZT",
            )
            db.add(court)
            await db.flush()

            # Generate slots for next 14 days
            today = date.today()
            for day_offset in range(14):
                slot_date = today + timedelta(days=day_offset)
                for hour in range(8, 22):
                    db.add(CourtSlot(
                        court_id=court.id,
                        slot_date=slot_date,
                        start_time=time(hour, 0),
                        end_time=time(hour + 1, 0),
                        status="available",
                    ))

        # Demo user
        user_result = await db.execute(select(User).where(User.email == "demo@thecampus.app"))
        if not user_result.scalar_one_or_none():
            user = User(
                email="demo@thecampus.app",
                hashed_password=hash_password("demo1234"),
                role="player",
                is_verified=True,
            )
            db.add(user)
            await db.flush()

            db.add(UserProfile(
                user_id=user.id,
                display_name="Demo Player",
                city="Алматы",
                onboarding_completed=True,
            ))
            db.add(UserSport(
                user_id=user.id,
                sport_id=sport_map["padel"],
                level="amateur",
            ))

        await db.commit()
        print("✓ Seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
