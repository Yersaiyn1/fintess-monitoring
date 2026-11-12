"""
Doctor-facing endpoints for reading patient health data.

ALL endpoints MUST use the `get_verified_doctor` dependency which enforces
the access_end > now() check in SQL — no endpoint can bypass it.
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.api.deps import get_verified_doctor
from app.models.health_reading import HealthReading
from app.models.device import Device
from app.schemas.health_reading import HealthReadingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/patients/{user_id}/readings", response_model=List[HealthReadingResponse])
async def get_patient_readings(
    user_id: int,
    from_dt: Optional[datetime] = Query(None),
    to_dt: Optional[datetime] = Query(None),
    access: dict = Depends(get_verified_doctor),
):
    """
    Return Health_Readings for a patient.
    Access verified in SQL (access_end > now()) by get_verified_doctor dependency.
    Optional date range filtering is also done in SQL.
    """
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
    readings = result.scalars().all()
    # Shadow RLS check
    try:
        from app.utils.rls_shadow import log_rls_mismatch
        await log_rls_mismatch(session=db, endpoint="/api/v1/doctor/patients/{user_id}/readings", user_id=None, doctor_id=access.get("doctor_id"), stmt=stmt)
    except Exception as exc:
        logger.warning(f"Shadow check failed non-critically: {exc}")
    return readings
