from datetime import date
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class DailyActivity(BaseModel):
    """DTO matching the frontend `DailyActivity` interface."""
    date: date = Field(..., description="ISO date (yyyy-mm-dd)")
    label: str = Field(..., description='Short weekday label, e.g. "Mon"')
    steps: int = Field(..., ge=0, description="Step count for the day")
    calories: float = Field(..., ge=0, description="Calories burned")
    distanceKm: float = Field(..., ge=0, description="Distance in kilometres")
    activeMinutes: int = Field(..., ge=0, description="Active minutes for the day")

    model_config = ConfigDict(from_attributes=True)


class DashboardResponse(BaseModel):
    """Response model for GET /api/dashboard/{user_id}."""
    user_id: int = Field(..., description="ID of the user")
    week: List[DailyActivity] = Field(
        ..., description="List of 7 days, oldest first, today last"
    )

    model_config = ConfigDict(from_attributes=True)

