"""Workout business logic: Phase 2 (start / stop / active) and Phase 3 (history queries)."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workout import Workout
from app.schemas.workout import ActivityTypeResponse, WorkoutResponse


@dataclass(frozen=True)
class ActivityType:
    kind: str
    label: str
    steps_per_min: float
    km_per_min: float
    kcal_per_min: float


# Estimated rates per minute. They are sent to the frontend (GET /workouts/types) so the live
# numbers on the Activity page and the final numbers saved here come from the SAME table.
# Real band data can replace this later without changing the API.
ACTIVITY_TYPES: tuple[ActivityType, ...] = (
    ActivityType("Run", "Run", 160, 0.16, 11.0),
    ActivityType("Walk", "Walk", 105, 0.075, 4.5),
    ActivityType("Cycling", "Cycling", 0, 0.33, 8.0),
    ActivityType("Strength", "Strength", 0, 0, 6.0),
    ActivityType("Yoga", "Yoga", 0, 0, 3.0),
)
_BY_KIND = {t.kind: t for t in ACTIVITY_TYPES}


class ActiveWorkoutExists(Exception):
    pass


class WorkoutNotFound(Exception):
    pass


class WorkoutAlreadyStopped(Exception):
    pass


def _utcnow() -> datetime:  # separate function so tests can control the clock
    return datetime.now(timezone.utc)


def aware(dt: datetime) -> datetime:
    """SQLite (used in tests) returns naive datetimes; PostgreSQL returns aware ones."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def duration_seconds(w: Workout) -> int | None:
    if w.ended_at is None:
        return None
    return max(0, round((aware(w.ended_at) - aware(w.started_at)).total_seconds()))


def activity_types() -> list[ActivityTypeResponse]:
    return [
        ActivityTypeResponse(
            kind=t.kind, label=t.label, stepsPerMin=t.steps_per_min,
            kmPerMin=t.km_per_min, kcalPerMin=t.kcal_per_min,
        )
        for t in ACTIVITY_TYPES
    ]


def compute_metrics(kind: str, duration_sec: float) -> tuple[int, float, float]:
    """(steps, distance_km, calories) for a finished workout."""
    rates = _BY_KIND[kind]
    minutes = duration_sec / 60
    return (
        round(rates.steps_per_min * minutes),
        round(rates.km_per_min * minutes, 2),
        round(rates.kcal_per_min * minutes, 1),
    )


def to_response(w: Workout) -> WorkoutResponse:
    return WorkoutResponse(
        id=w.workout_id,
        kind=w.kind,
        startedAt=aware(w.started_at),
        endedAt=aware(w.ended_at) if w.ended_at else None,
        durationSec=duration_seconds(w),
        steps=w.steps,
        distanceKm=float(w.distance_km),
        caloriesKcal=float(w.calories_kcal),
        inProgress=w.ended_at is None,
    )


# ---------------------------------------------------------------- Phase 2: tracking
async def get_active(db: AsyncSession, user_id: int) -> Workout | None:
    result = await db.execute(
        select(Workout).where(Workout.user_id == user_id, Workout.ended_at.is_(None))
    )
    return result.scalar_one_or_none()


async def start_workout(db: AsyncSession, user_id: int, kind: str) -> Workout:
    if await get_active(db, user_id) is not None:
        raise ActiveWorkoutExists
    workout = Workout(user_id=user_id, kind=kind, started_at=_utcnow())
    db.add(workout)
    try:
        await db.commit()
    except IntegrityError:  # two parallel "start" requests: the unique index lets only one through
        await db.rollback()
        raise ActiveWorkoutExists
    await db.refresh(workout)
    return workout


async def stop_workout(db: AsyncSession, user_id: int, workout_id: int) -> Workout:
    result = await db.execute(
        select(Workout).where(Workout.workout_id == workout_id, Workout.user_id == user_id).with_for_update()
    )
    workout = result.scalar_one_or_none()
    if workout is None:
        raise WorkoutNotFound
    if workout.ended_at is not None:
        raise WorkoutAlreadyStopped
    now = _utcnow()
    seconds = max(0.0, (now - aware(workout.started_at)).total_seconds())
    workout.ended_at = now
    workout.steps, workout.distance_km, workout.calories_kcal = compute_metrics(workout.kind, seconds)
    await db.commit()
    await db.refresh(workout)
    return workout


# ---------------------------------------------------------------- Phase 3: history
async def get_workout(db: AsyncSession, user_id: int, workout_id: int) -> Workout:
    result = await db.execute(
        select(Workout).where(Workout.workout_id == workout_id, Workout.user_id == user_id)
    )
    workout = result.scalar_one_or_none()
    if workout is None:
        raise WorkoutNotFound
    return workout


async def list_workouts(
    db: AsyncSession,
    user_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    kind: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Workout], int]:
    """Finished workouts of the user, newest first. Dates are inclusive UTC days."""
    conditions = [Workout.user_id == user_id, Workout.ended_at.is_not(None)]
    if date_from:
        conditions.append(Workout.started_at >= day_start(date_from))
    if date_to:
        conditions.append(Workout.started_at < day_start(date_to + timedelta(days=1)))
    if kind:
        conditions.append(Workout.kind == kind)

    total = (await db.execute(select(func.count()).select_from(Workout).where(*conditions))).scalar_one()
    rows = await db.execute(
        select(Workout).where(*conditions)
        .order_by(Workout.started_at.desc(), Workout.workout_id.desc())
        .limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


async def finished_between(db: AsyncSession, user_id: int, first_day: date, last_day: date) -> list[Workout]:
    """Finished workouts that started between two UTC days (inclusive). Used by dashboard and analytics."""
    rows = await db.execute(
        select(Workout).where(
            Workout.user_id == user_id,
            Workout.ended_at.is_not(None),
            Workout.started_at >= day_start(first_day),
            Workout.started_at < day_start(last_day + timedelta(days=1)),
        )
    )
    return list(rows.scalars().all())
