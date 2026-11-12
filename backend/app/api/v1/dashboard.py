from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import build_week

router = APIRouter()


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Aggregated activity of the current user for the last 7 days",
)
async def get_dashboard(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> DashboardResponse:
    """The list is ordered oldest -> newest; the last element is today (UTC).

    The user is taken from the access token, so nobody can read another user's data.
    """
    return DashboardResponse(user_id=user.user_id, week=await build_week(db, user.user_id))
