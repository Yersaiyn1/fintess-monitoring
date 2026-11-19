import logging

from fastapi import Depends, HTTPException, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    ROLE_DOCTOR,
    ROLE_USER,
    InvalidTokenError,
    TokenPayload,
    decode_access_token,
)
from app.db.session import get_db
from app.models.access_log import AccessLog
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.user import User

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authenticate(
    credentials: HTTPAuthorizationCredentials | None, required_role: str
) -> TokenPayload:
    """Central JWT check used by every role-specific dependency.

    * no / malformed / badly signed / expired token, unknown or missing role -> 401
    * valid token of ANOTHER role (e.g. a doctor token on a user endpoint)  -> 403
    Identity comes only from the verified token, never from client-supplied headers.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        logger.info("Rejected access token: %s", exc)
        raise _unauthorized()
    if payload.role != required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This token is not allowed to use this endpoint.",
        )
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the logged-in user from a `role=user` Bearer token (401 / 403 otherwise)."""
    payload = _authenticate(credentials, ROLE_USER)
    user = await db.get(User, payload.subject_id)
    if user is None:
        raise _unauthorized()
    return user


async def get_current_doctor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Doctor:
    """Return the logged-in active doctor from a `role=doctor` Bearer token (401 / 403 otherwise)."""
    payload = _authenticate(credentials, ROLE_DOCTOR)
    doctor = await db.get(Doctor, payload.subject_id)
    if doctor is None or not doctor.is_active:
        raise _unauthorized()
    return doctor


async def get_verified_doctor(
    request: Request,
    user_id: int = Path(..., description="Patient user ID being accessed"),
    doctor: Doctor = Depends(get_current_doctor),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify that the authenticated doctor has an active permission for `user_id`.

    Business rule enforced directly in SQL (both dates inclusive):
        access_start <= CURRENT_DATE <= access_end
    """
    result = await db.execute(
        select(DoctorAccess).where(
            and_(
                DoctorAccess.doctor_id == doctor.doctor_id,
                DoctorAccess.user_id == user_id,
                DoctorAccess.access_start <= func.current_date(),
                DoctorAccess.access_end >= func.current_date(),
            )
        )
    )
    access = result.scalar_one_or_none()
    endpoint = request.url.path if request else "/api/v1/doctor"

    # Record audit trail when patient exists (satisfies FK on Access_Log.user_id).
    patient = await db.get(User, user_id)
    if patient is not None:
        log_entry = AccessLog(
            doctor_id=doctor.doctor_id,
            user_id=user_id,
            endpoint=endpoint,
            result="GRANTED" if access is not None else "DENIED",
        )
        db.add(log_entry)
        await db.commit()

    if access is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor does not have active access to this patient's data.",
        )
    return {"doctor_id": doctor.doctor_id, "user_id": user_id, "doctor": doctor, "db": db}
