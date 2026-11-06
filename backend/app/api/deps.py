from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.session import get_db
from app.models.doctor_access import DoctorAccess
from app.models.access_log import AccessLog
import logging

logger = logging.getLogger(__name__)


async def get_verified_doctor(
    x_doctor_id: int = Header(..., description="Doctor ID from auth header"),
    x_user_id: int = Header(..., description="Patient user ID being accessed"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Dependency that verifies doctor has ACTIVE access to the patient's data.
    Filters access_end > now() directly in SQL — cannot be bypassed by endpoint code.
    Returns dict with doctor_id and user_id.
    Raises HTTP 403 if access is expired or not found.
    """
    result = await db.execute(
        select(DoctorAccess).where(
            and_(
                DoctorAccess.doctor_id == x_doctor_id,
                DoctorAccess.user_id == x_user_id,
                DoctorAccess.access_end > func.current_date(),
                DoctorAccess.access_start <= func.current_date(),
            )
        )
    )
    access = result.scalar_one_or_none()
    if access is None:
        # Log the denied attempt
        log_entry = AccessLog(
            doctor_id=x_doctor_id,
            user_id=x_user_id,
            endpoint="<checked_in_dep>",
            result="DENIED",
        )
        db.add(log_entry)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor does not have active access to this patient's data.",
        )
    return {"doctor_id": x_doctor_id, "user_id": x_user_id, "db": db}
