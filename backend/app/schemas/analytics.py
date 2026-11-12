from datetime import date as date_type
from typing import List, Literal

from pydantic import BaseModel

Period = Literal["week", "month"]


class AnalyticsDay(BaseModel):
    date: date_type
    label: str            # weekday ("Mon") for week, day of month ("12") for month
    workouts: int
    durationMin: float
    caloriesKcal: float
    distanceKm: float
    steps: int


class AnalyticsTotals(BaseModel):
    workouts: int
    durationMin: float
    caloriesKcal: float
    distanceKm: float
    steps: int


class KindBreakdown(BaseModel):
    kind: str
    workouts: int
    durationMin: float
    caloriesKcal: float


class AnalyticsResponse(BaseModel):
    period: Period
    startDate: date_type
    endDate: date_type
    days: List[AnalyticsDay]       # oldest first, one item per day (zeros when nothing happened)
    totals: AnalyticsTotals
    byKind: List[KindBreakdown]    # sorted by time spent, biggest first
