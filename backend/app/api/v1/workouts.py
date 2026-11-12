"""Workout endpoints. Phase 2: types, active, start, stop.  Phase 3: list (filters) and details.

NOTE: static paths (/types, /active) are declared BEFORE /{workout_id}, otherwise "types" would be
read as an id.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.workout import (
    ActivityTypeResponse, StartWorkoutRequest, WorkoutKind, WorkoutListResponse, WorkoutResponse,
)
from app.services import workouts as svc

router = APIRouter()


# ---------------------------------------------------------------- Phase 2
@router.get("/types", response_model=List[ActivityTypeResponse], summary="Activity types and their rates")
async def activity_types(user: User = Depends(get_current_user)):
    return svc.activity_types()


@router.get("/active", response_model=Optional[WorkoutResponse], summary="The workout in progress (or null)")
async def active_workout(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    workout = await svc.get_active(db, user.user_id)
    return svc.to_response(workout) if workout else None


@router.post("/start", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def start_workout(
    payload: StartWorkoutRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        workout = await svc.start_workout(db, user.user_id, payload.kind)
    except svc.ActiveWorkoutExists:
        raise HTTPException(status.HTTP_409_CONFLICT, "A workout is already in progress. Stop it first.")
    return svc.to_response(workout)


@router.post("/{workout_id}/stop", response_model=WorkoutResponse)
async def stop_workout(workout_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        workout = await svc.stop_workout(db, user.user_id, workout_id)
    except svc.WorkoutNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout not found.")
    except svc.WorkoutAlreadyStopped:
        raise HTTPException(status.HTTP_409_CONFLICT, "This workout is already stopped.")
    return svc.to_response(workout)


# ---------------------------------------------------------------- Phase 3
@router.get("", response_model=WorkoutListResponse, summary="Finished workouts (newest first) with filters")
async def list_workouts(
    date_from: Optional[date] = Query(None, alias="from", description="first day, inclusive (UTC)"),
    date_to: Optional[date] = Query(None, alias="to", description="last day, inclusive (UTC)"),
    kind: Optional[WorkoutKind] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "'from' must not be after 'to'.")
    items, total = await svc.list_workouts(
        db, user.user_id, date_from=date_from, date_to=date_to, kind=kind, limit=limit, offset=offset
    )
    return WorkoutListResponse(items=[svc.to_response(w) for w in items], total=total, limit=limit, offset=offset)


@router.get("/{workout_id}", response_model=WorkoutResponse, summary="Workout details")
async def workout_details(workout_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        return svc.to_response(await svc.get_workout(db, user.user_id, workout_id))
    except svc.WorkoutNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout not found.")
