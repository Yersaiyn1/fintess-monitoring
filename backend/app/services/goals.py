"""Phase 4 business logic: user goals, live progress tracking, and health/inactivity alerts."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.goal import Goal
from app.models.health_reading import HealthReading
from app.schemas.goal import (
    GoalProgressResponse,
    GoalUpsertRequest,
    GoalsSummaryResponse,
    HealthAlertsResponse,
)
from app.services.dashboard import build_week
from app.services.workouts import aware, finished_between


class GoalNotFound(Exception):
    pass


async def _current_metric_totals(
    db: AsyncSession, user_id: int, today: date
) -> tuple[dict[tuple[str, str], float], int, int]:
    """Return `(totals_by_period_and_metric, active_days_7d, weekly_workouts)`."""
    first_day = today - timedelta(days=6)
    week = await build_week(db, user_id, today=today)
    workouts = await finished_between(db, user_id, first_day, today)

    daily_workouts = sum(1 for w in workouts if aware(w.started_at).date() == today)
    weekly_workouts = len(workouts)

    today_row = week[-1]
    totals: dict[tuple[str, str], float] = {
        ("daily", "steps"): float(today_row.steps),
        ("daily", "calories_kcal"): round(float(today_row.calories), 1),
        ("daily", "distance_km"): round(float(today_row.distanceKm), 2),
        ("daily", "active_minutes"): float(today_row.activeMinutes),
        ("daily", "workouts"): float(daily_workouts),
        ("weekly", "steps"): float(sum(d.steps for d in week)),
        ("weekly", "calories_kcal"): round(float(sum(d.calories for d in week)), 1),
        ("weekly", "distance_km"): round(float(sum(d.distanceKm for d in week)), 2),
        ("weekly", "active_minutes"): float(sum(d.activeMinutes for d in week)),
        ("weekly", "workouts"): float(weekly_workouts),
    }

    active_days_7d = sum(
        1 for d in week if d.steps > 0 or d.calories > 0 or d.activeMinutes > 0
    )
    return totals, active_days_7d, weekly_workouts


def _to_progress(goal: Goal, totals: dict[tuple[str, str], float]) -> GoalProgressResponse:
    current = totals.get((goal.period, goal.metric), 0.0)
    pct = min(100, max(0, round((current / goal.target_value) * 100)))
    return GoalProgressResponse(
        goal_id=goal.goal_id,
        period=goal.period,
        metric=goal.metric,
        target_value=round(float(goal.target_value), 2),
        current_value=round(float(current), 2),
        progress_percent=pct,
        achieved=current >= goal.target_value,
    )


async def build_alerts(
    db: AsyncSession,
    user_id: int,
    today: date | None = None,
    *,
    active_days_7d: int | None = None,
    weekly_workouts: int | None = None,
) -> HealthAlertsResponse:
    """Compute 7-day high heart rate (> 100 bpm) and 7-day inactivity alerts."""
    today = today or datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=6)
    start_dt = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)

    if active_days_7d is None or weekly_workouts is None:
        _, active_days_7d, weekly_workouts = await _current_metric_totals(db, user_id, today)

    hr_stmt = (
        select(
            func.avg(HealthReading.heart_rate_bpm),
            func.count(HealthReading.heart_rate_bpm),
        )
        .join(Device, HealthReading.device_id == Device.device_id)
        .where(
            Device.user_id == user_id,
            HealthReading.date_time >= start_dt,
            HealthReading.date_time < end_dt,
            HealthReading.heart_rate_bpm.is_not(None),
        )
    )
    avg_raw, hr_count = (await db.execute(hr_stmt)).one()
    hr_count = int(hr_count or 0)
    avg_hr = round(float(avg_raw), 1) if avg_raw is not None and hr_count > 0 else None

    high_hr_alert = avg_hr is not None and avg_hr > 100.0
    inactivity_alert = active_days_7d == 0 and weekly_workouts == 0

    messages: list[str] = []
    if high_hr_alert:
        messages.append(
            f"Average heart rate over the last 7 days is {avg_hr} bpm (> 100 bpm)."
        )
    if inactivity_alert:
        messages.append(
            "No activity or workouts recorded in the last 7 days."
        )

    return HealthAlertsResponse(
        high_heart_rate_alert=high_hr_alert,
        avg_heart_rate_7d=avg_hr,
        heart_rate_readings_7d=hr_count,
        inactivity_alert=inactivity_alert,
        active_days_7d=active_days_7d,
        messages=messages,
    )


async def build_goals_summary(
    db: AsyncSession, user_id: int, today: date | None = None
) -> GoalsSummaryResponse:
    today = today or datetime.now(timezone.utc).date()
    totals, active_days_7d, weekly_workouts = await _current_metric_totals(db, user_id, today)
    alerts = await build_alerts(
        db,
        user_id,
        today=today,
        active_days_7d=active_days_7d,
        weekly_workouts=weekly_workouts,
    )

    rows = (
        await db.execute(
            select(Goal)
            .where(Goal.user_id == user_id)
            .order_by(Goal.period.asc(), Goal.metric.asc())
        )
    ).scalars().all()

    return GoalsSummaryResponse(
        goals=[_to_progress(g, totals) for g in rows],
        alerts=alerts,
    )


async def upsert_goal(
    db: AsyncSession, user_id: int, payload: GoalUpsertRequest, today: date | None = None
) -> GoalProgressResponse:
    existing = (
        await db.execute(
            select(Goal).where(
                Goal.user_id == user_id,
                Goal.period == payload.period,
                Goal.metric == payload.metric,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        goal = Goal(
            user_id=user_id,
            period=payload.period,
            metric=payload.metric,
            target_value=payload.target_value,
        )
        db.add(goal)
    else:
        existing.target_value = payload.target_value
        goal = existing

    await db.commit()
    await db.refresh(goal)

    today = today or datetime.now(timezone.utc).date()
    totals, _, _ = await _current_metric_totals(db, user_id, today)
    return _to_progress(goal, totals)


async def delete_goal(db: AsyncSession, user_id: int, goal_id: int) -> None:
    goal = (
        await db.execute(
            select(Goal).where(Goal.goal_id == goal_id, Goal.user_id == user_id)
        )
    ).scalar_one_or_none()
    if goal is None:
        raise GoalNotFound
    await db.delete(goal)
    await db.commit()
