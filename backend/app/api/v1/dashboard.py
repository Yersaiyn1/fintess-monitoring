from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.health_reading import HealthReading
from app.models.device import Device
from app.models.user import User
from app.schemas.dashboard import DashboardResponse, DailyActivity

router = APIRouter()

@router.get(
    "/dashboard/{user_id}",
    response_model=DashboardResponse,
    tags=["Dashboard"],
    summary="Aggregated activity for the last 7 days",
)
async def get_dashboard(
    user_id: int, db: AsyncSession = Depends(get_db)
) -> DashboardResponse:
    """Return steps, calories, distance and active minutes for the past week.

    The list is ordered oldest → newest; the last element corresponds to today.
    Distance and active minutes use the same simple formulas the mock data
    employed (distance = steps * 0.00075 km, active minutes ≈ steps / 100).
    """
    # 7‑day window, inclusive of today
    seven_days_ago = datetime.utcnow() - timedelta(days=6)

    stmt = (
        select(
            func.date_trunc("day", HealthReading.date_time).label("day"),
            func.sum(HealthReading.steps).label("steps"),
            func.sum(HealthReading.calories_kcal).label("calories"),
        )
        .join(Device, HealthReading.device_id == Device.device_id)
        .join(User, Device.user_id == User.user_id)
        .where(
            User.user_id == user_id,
            HealthReading.date_time >= seven_days_ago,
        )
        .group_by("day")
        .order_by("day")
    )

    result = await db.execute(stmt)
    rows = result.fetchall()

    # Build dict keyed by date for fast lookup
    activity_by_date = {
        row.day.date(): {"steps": row.steps or 0, "calories": float(row.calories or 0)}
        for row in rows
    }

    # Populate full 7‑day list (oldest first)
    week: list[DailyActivity] = []
    today = datetime.utcnow().date()
    for i in range(7):
        day = today - timedelta(days=6 - i)
        data = activity_by_date.get(day, {"steps": 0, "calories": 0.0})
        steps = data["steps"]
        calories = data["calories"]
        distance = round(steps * 0.00075, 2)
        active_minutes = int(round(steps / 100))
        week.append(
            DailyActivity(
                date=day,
                label=day.strftime("%a"),
                steps=steps,
                calories=calories,
                distanceKm=distance,
                activeMinutes=active_minutes,
            )
        )

    return DashboardResponse(user_id=user_id, week=week)

