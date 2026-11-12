"""DTOs for workouts. Field names are camelCase to match the Angular models exactly."""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

WorkoutKind = Literal["Run", "Walk", "Cycling", "Strength", "Yoga"]


class ActivityTypeResponse(BaseModel):
    """One selectable activity type with the rates used to estimate steps/distance/calories."""
    kind: WorkoutKind
    label: str
    stepsPerMin: float
    kmPerMin: float
    kcalPerMin: float


class StartWorkoutRequest(BaseModel):
    kind: WorkoutKind


class WorkoutResponse(BaseModel):
    id: int
    kind: WorkoutKind
    startedAt: datetime
    endedAt: Optional[datetime] = None
    durationSec: Optional[int] = None  # None while the workout is in progress
    steps: int
    distanceKm: float
    caloriesKcal: float
    inProgress: bool


class WorkoutListResponse(BaseModel):
    items: List[WorkoutResponse]
    total: int
    limit: int
    offset: int
