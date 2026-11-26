"""Server-persisted user goals service."""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_goal import UserGoal
from app.schemas.goals import (
    DEFAULT_STEPS_DAILY,
    DEFAULT_WORKOUTS_WEEKLY,
    UserGoalsResponse,
    UserGoalsUpdate,
)


async def get_user_goals(db: AsyncSession, user_id: int) -> UserGoalsResponse:
    """Return user's goals, falling back to defaults without creating a DB row."""
    goal = await db.get(UserGoal, user_id)
    if goal is None:
        return UserGoalsResponse(
            steps_daily=DEFAULT_STEPS_DAILY,
            workouts_weekly=DEFAULT_WORKOUTS_WEEKLY,
            updated_at=None,
        )
    return UserGoalsResponse.model_validate(goal)


async def upsert_user_goals(
    db: AsyncSession, user_id: int, payload: UserGoalsUpdate
) -> UserGoalsResponse:
    """Create or update the user's daily step and weekly workout targets."""
    now = datetime.now(timezone.utc)
    goal = await db.get(UserGoal, user_id)
    if goal is None:
        goal = UserGoal(
            user_id=user_id,
            steps_daily=payload.steps_daily,
            workouts_weekly=payload.workouts_weekly,
            updated_at=now,
        )
        db.add(goal)
    else:
        goal.steps_daily = payload.steps_daily
        goal.workouts_weekly = payload.workouts_weekly
        goal.updated_at = now
    await db.commit()
    await db.refresh(goal)
    return UserGoalsResponse.model_validate(goal)
