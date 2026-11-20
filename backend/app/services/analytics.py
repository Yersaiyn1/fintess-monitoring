"""Weekly and monthly activity analytics with workout breakdowns."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.analytics import AnalyticsDay, AnalyticsResponse, AnalyticsTotals, KindBreakdown
from app.services.dashboard import build_daily_activity
from app.services.workouts import aware, duration_seconds, finished_between

PERIOD_DAYS = {"week": 7, "month": 30}


async def build_analytics(
    db: AsyncSession, user_id: int, period: str, today: date | None = None
) -> AnalyticsResponse:
    """Per-day totals for the last 7 (week) or 30 (month) days, ending today (UTC)."""
    today = today or datetime.now(timezone.utc).date()
    n = PERIOD_DAYS[period]
    first_day = today - timedelta(days=n - 1)
    workouts = await finished_between(db, user_id, first_day, today)

    activity = await build_daily_activity(db, user_id, first_day, today, workouts)
    workout_counts = Counter(aware(w.started_at).date() for w in workouts)
    per_kind = defaultdict(lambda: {"workouts": 0, "sec": 0, "kcal": 0.0})
    for w in workouts:
        sec = duration_seconds(w) or 0
        k = per_kind[w.kind]
        k["workouts"] += 1; k["sec"] += sec; k["kcal"] += float(w.calories_kcal)

    days: list[AnalyticsDay] = []
    for day in activity:
        days.append(AnalyticsDay(
            date=day.date,
            label=day.label if period == "week" else str(day.date.day),
            workouts=workout_counts[day.date],
            durationMin=day.activeMinutes,
            caloriesKcal=day.calories,
            distanceKm=day.distanceKm,
            steps=day.steps,
        ))

    totals = AnalyticsTotals(
        workouts=sum(d.workouts for d in days),
        durationMin=round(sum(d.durationMin for d in days), 1),
        caloriesKcal=round(sum(d.caloriesKcal for d in days), 1),
        distanceKm=round(sum(d.distanceKm for d in days), 2),
        steps=sum(d.steps for d in days),
    )
    by_kind = sorted(
        (KindBreakdown(kind=k, workouts=v["workouts"], durationMin=round(v["sec"] / 60, 1), caloriesKcal=round(v["kcal"], 1))
         for k, v in per_kind.items()),
        key=lambda x: x.durationMin, reverse=True,
    )
    return AnalyticsResponse(
        period=period, startDate=first_day, endDate=today, days=days, totals=totals, byKind=by_kind
    )
