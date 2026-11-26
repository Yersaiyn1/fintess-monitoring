"""API registry (all endpoints live under /api/v1).

To add a feature/phase: create app/api/v1/<feature>.py with its own APIRouter
and add ONE line below.
"""
from fastapi import APIRouter

from app.api.v1 import analytics, auth, dashboard, doctor, goals, sync, workouts

api_router = APIRouter()

# Baseline + Phase 1 (auth, dashboard)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(doctor.router, prefix="/doctor", tags=["doctor"])

# Phase 2 — Activity Tracking
api_router.include_router(workouts.router, prefix="/workouts", tags=["workouts"])  # Phase 3 adds list/details here
# Phase 3 — History & Analytics
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

# Phase 4 — Goals & Settings:      goals.router (/goals), settings.router (/settings)
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
