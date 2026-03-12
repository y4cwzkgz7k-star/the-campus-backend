from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.sport import Sport
from app.schemas.sport import SportOut

router = APIRouter(prefix="/sports", tags=["sports"])


@router.get("/", response_model=list[SportOut])
async def list_sports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Sport).where(Sport.is_active == True).order_by(Sport.name))
    return result.scalars().all()
