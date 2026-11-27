from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.goals import UserGoalsResponse, UserGoalsUpdate
from app.services.goals import get_user_goals, upsert_user_goals

router = APIRouter()


@router.get("", response_model=UserGoalsResponse, summary="Get current user's fitness goals")
async def read_goals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserGoalsResponse:
    """Return the user's saved targets, or default values if none are saved yet."""
    return await get_user_goals(db, user.user_id)


@router.put("", response_model=UserGoalsResponse, summary="Update current user's fitness goals")
async def save_goals(
    payload: UserGoalsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserGoalsResponse:
    """Persist daily step and weekly workout goals on the server."""
    return await upsert_user_goals(db, user.user_id, payload)
