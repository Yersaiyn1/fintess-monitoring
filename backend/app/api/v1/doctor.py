"""
Doctor-facing endpoints (read-only patient data) and patient-facing Doctor_Access management.

Authorization architecture (Variant B — application-level authorization):
- Doctor identity comes exclusively from a verified `role="doctor"` Bearer JWT.
- Patient access is verified in SQL (`access_start <= CURRENT_DATE <= access_end`,
  both boundary dates inclusive) by `get_verified_doctor` in `app/api/deps.py`.
- Every access check is recorded in `Access_Log` (`GRANTED` / `DENIED`).
- Patients (`role="user"` JWT) manage their own `Doctor_Access` records via `/access` endpoints.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_doctor, get_current_user, get_verified_doctor
from app.db.session import get_db
from app.models.device import Device
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.health_reading import HealthReading
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.doctor import (
    DoctorAccessDetailResponse,
    DoctorAccessGrantRequest,
    DoctorResponse,
)
from app.schemas.health_reading import HealthReadingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/directory", response_model=List[DoctorResponse])
async def list_doctor_directory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all active doctors available to grant access to (authenticated user)."""
    stmt = (
        select(Doctor)
        .where(Doctor.is_active.is_(True))
        .order_by(Doctor.doctor_id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/access", response_model=List[DoctorAccessDetailResponse])
async def list_my_doctor_access(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all doctor access permissions granted by the current user."""
    stmt = (
        select(DoctorAccess, Doctor)
        .join(Doctor, DoctorAccess.doctor_id == Doctor.doctor_id)
        .where(DoctorAccess.user_id == user.user_id)
        .order_by(DoctorAccess.access_end.desc(), Doctor.doctor_id.asc())
    )
    rows = (await db.execute(stmt)).all()
    today = datetime.now(timezone.utc).date()
    return [
        DoctorAccessDetailResponse(
            user_id=access.user_id,
            doctor_id=access.doctor_id,
            doctor_name=doc.full_name,
            specialty=doc.specialty,
            license_number=doc.license_number,
            access_start=access.access_start,
            access_end=access.access_end,
            is_active=access.access_start <= today <= access.access_end,
        )
        for access, doc in rows
    ]


@router.post(
    "/access",
    response_model=DoctorAccessDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_or_update_doctor_access(
    payload: DoctorAccessGrantRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant or update time-bounded read-only access for a doctor to the current user's data."""
    doc = (
        await db.execute(
            select(Doctor).where(
                Doctor.doctor_id == payload.doctor_id,
                Doctor.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found.")

    existing = (
        await db.execute(
            select(DoctorAccess).where(
                DoctorAccess.user_id == user.user_id,
                DoctorAccess.doctor_id == payload.doctor_id,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        access = DoctorAccess(
            user_id=user.user_id,
            doctor_id=payload.doctor_id,
            access_start=payload.access_start,
            access_end=payload.access_end,
        )
        db.add(access)
    else:
        existing.access_start = payload.access_start
        existing.access_end = payload.access_end
        access = existing

    await db.commit()
    await db.refresh(access)

    today = datetime.now(timezone.utc).date()
    return DoctorAccessDetailResponse(
        user_id=access.user_id,
        doctor_id=access.doctor_id,
        doctor_name=doc.full_name,
        specialty=doc.specialty,
        license_number=doc.license_number,
        access_start=access.access_start,
        access_end=access.access_end,
        is_active=access.access_start <= today <= access.access_end,
    )


@router.delete("/access/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_doctor_access(
    doctor_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a doctor's access to the current user's health data."""
    existing = (
        await db.execute(
            select(DoctorAccess).where(
                DoctorAccess.user_id == user.user_id,
                DoctorAccess.doctor_id == doctor_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Access permission not found.")

    await db.delete(existing)
    await db.commit()


@router.get("/patients", response_model=List[UserResponse])
async def list_accessible_patients(
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Return patients who currently grant active access to the authenticated doctor."""
    stmt = (
        select(User)
        .join(DoctorAccess, DoctorAccess.user_id == User.user_id)
        .where(
            and_(
                DoctorAccess.doctor_id == doctor.doctor_id,
                DoctorAccess.access_start <= func.current_date(),
                DoctorAccess.access_end >= func.current_date(),
            )
        )
        .order_by(User.user_id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/patients/{user_id}/readings", response_model=List[HealthReadingResponse])
async def get_patient_readings(
    user_id: int,
    from_dt: Optional[datetime] = Query(None),
    to_dt: Optional[datetime] = Query(None),
    access: dict = Depends(get_verified_doctor),
):
    """Return Health_Readings for a patient when the doctor has active permission."""
    db: AsyncSession = access["db"]

    conditions = [Device.user_id == user_id]
    if from_dt:
        conditions.append(HealthReading.date_time >= from_dt)
    if to_dt:
        conditions.append(HealthReading.date_time <= to_dt)

    stmt = (
        select(HealthReading)
        .join(Device, HealthReading.device_id == Device.device_id)
        .where(and_(*conditions))
        .order_by(HealthReading.date_time.desc())
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())
