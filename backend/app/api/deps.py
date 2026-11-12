from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
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
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


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
