from typing import Literal

from pydantic import BaseModel, Field

GoalPeriod = Literal["daily", "weekly"]
GoalMetric = Literal["steps", "calories_kcal", "distance_km", "active_minutes", "workouts"]


class GoalUpsertRequest(BaseModel):
    period: GoalPeriod
    metric: GoalMetric
    target_value: float = Field(..., gt=0, le=1_000_000)


class GoalProgressResponse(BaseModel):
    goal_id: int
    period: GoalPeriod
    metric: GoalMetric
    target_value: float
    current_value: float
    progress_percent: int
    achieved: bool


class HealthAlertsResponse(BaseModel):
    high_heart_rate_alert: bool
    avg_heart_rate_7d: float | None = None
    heart_rate_readings_7d: int
    inactivity_alert: bool
    active_days_7d: int
    messages: list[str]


class GoalsSummaryResponse(BaseModel):
    goals: list[GoalProgressResponse]
    alerts: HealthAlertsResponse
