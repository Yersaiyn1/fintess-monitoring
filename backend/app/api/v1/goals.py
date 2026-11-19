"""Phase 4 endpoints: personal activity goals, progress tracking, and health alerts."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.goal import (
    GoalProgressResponse,
    GoalUpsertRequest,
    GoalsSummaryResponse,
)
from app.services import goals as svc

router = APIRouter()


@router.get("", response_model=GoalsSummaryResponse, summary="User goals with live progress and 7-day alerts")
async def get_goals_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.build_goals_summary(db, user.user_id)


@router.post(
    "",
    response_model=GoalProgressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a daily/weekly goal",
)
async def upsert_goal(
    payload: GoalUpsertRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await svc.upsert_goal(db, user.user_id, payload)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a goal")
async def delete_goal(
    goal_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_goal(db, user.user_id, goal_id)
    except svc.GoalNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal not found.")
