from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.access_log import AccessLog
import logging

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the logged-in user from the `Authorization: Bearer <token>` header (401 otherwise)."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials, expected_role="patient")
    if user_id is None:
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require both a signed admin-role token and the current DB admin flag."""
    unauthorized = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Administrator access required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials, expected_role="admin")
    if user_id is None:
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None or not user.is_admin:
        raise unauthorized
    return user


async def get_current_doctor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    """Return the authenticated doctor from a role-scoped bearer token."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated as a doctor.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    doctor_id = decode_access_token(credentials.credentials, expected_role="doctor")
    if doctor_id is None:
        raise unauthorized
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None or not doctor.email or not doctor.password_hash:
        raise unauthorized
    return doctor


async def get_verified_doctor(
    user_id: int,
    doctor: Doctor = Depends(get_current_doctor),
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
                DoctorAccess.doctor_id == doctor.doctor_id,
                DoctorAccess.user_id == user_id,
                DoctorAccess.access_end > func.current_date(),
                DoctorAccess.access_start <= func.current_date(),
            )
        )
    )
    access = result.scalar_one_or_none()
    if access is None:
        # Log the denied attempt
        log_entry = AccessLog(
            doctor_id=doctor.doctor_id,
            user_id=user_id,
            endpoint="<checked_in_dep>",
            result="DENIED",
        )
        db.add(log_entry)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor does not have active access to this patient's data.",
        )
    return {"doctor_id": doctor.doctor_id, "user_id": user_id, "db": db}
