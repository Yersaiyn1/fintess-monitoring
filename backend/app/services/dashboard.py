"""Dashboard aggregation (used by api/v1/dashboard.py)."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.health_reading import HealthReading
from app.schemas.dashboard import DailyActivity

DAYS = 7
STEP_LENGTH_KM = 0.00075      # ~75 cm per step
STEPS_PER_ACTIVE_MINUTE = 100  # simple estimate until workouts are tracked (Phase 2)
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _as_date(value) -> date:
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value)[:10])


async def build_week(db: AsyncSession, user_id: int, today: date | None = None) -> list[DailyActivity]:
    """Last 7 days (oldest first, today last) summed over all devices of the user.

    Days without readings are returned with zeros so the chart always has 7 bars.
    """
    today = today or datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=DAYS - 1)
    start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)

    day = func.date(HealthReading.date_time).label("day")
    stmt = (
        select(
            day,
            func.coalesce(func.sum(HealthReading.steps), 0),
            func.coalesce(func.sum(HealthReading.calories_kcal), 0),
        )
        .join(Device, HealthReading.device_id == Device.device_id)
        .where(
            Device.user_id == user_id,
            HealthReading.date_time >= start,
            HealthReading.date_time < end,
        )
        .group_by(day)
        .order_by(day)
    )
    rows = (await db.execute(stmt)).all()
    by_day = {_as_date(r[0]): (int(r[1]), float(r[2])) for r in rows}

    week: list[DailyActivity] = []
    for i in range(DAYS):
        d = first_day + timedelta(days=i)
        steps, calories = by_day.get(d, (0, 0.0))
        week.append(
            DailyActivity(
                date=d,
                label=_WEEKDAYS[d.weekday()],
                steps=steps,
                calories=round(calories, 1),
                distanceKm=round(steps * STEP_LENGTH_KM, 2),
                activeMinutes=round(steps / STEPS_PER_ACTIVE_MINUTE),
            )
        )
    return week
