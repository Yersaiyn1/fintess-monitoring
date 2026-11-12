from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse, Period
from app.services.analytics import build_analytics

router = APIRouter()


@router.get("/workouts", response_model=AnalyticsResponse, summary="Weekly or monthly workout analytics")
async def workout_analytics(
    period: Period = Query("week"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await build_analytics(db, user.user_id, period)
