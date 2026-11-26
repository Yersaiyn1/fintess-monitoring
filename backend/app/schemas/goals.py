from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_STEPS_DAILY = 10_000
DEFAULT_WORKOUTS_WEEKLY = 3


class UserGoalsUpdate(BaseModel):
    """Payload for updating the current user's fitness targets."""

    steps_daily: int = Field(..., ge=1000, le=100000)
    workouts_weekly: int = Field(..., ge=0, le=14)


class UserGoalsResponse(BaseModel):
    """User fitness goals returned by GET/PUT /api/v1/goals."""

    steps_daily: int = Field(..., ge=1000, le=100000)
    workouts_weekly: int = Field(..., ge=0, le=14)
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
