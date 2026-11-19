"""Authentication business logic (used by api/v1/auth.py)."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    ROLE_DOCTOR,
    ROLE_USER,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.doctor import Doctor
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import RegisterRequest

# Used to spend the same time on "unknown email" as on "wrong password".
_DUMMY_HASH = hash_password("dummy-password-1")

REFRESH_TOKEN_EXPIRE_DAYS = 14


class EmailAlreadyRegistered(Exception):
    pass


class InvalidRefreshToken(Exception):
    pass


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _utc_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    existing = await db.execute(select(User.user_id).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise EmailAlreadyRegistered
    user = User(
        full_name=data.full_name,
        email=data.email,
        birth_date=data.birth_date,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:  # two parallel registrations with the same email
        await db.rollback()
        raise EmailAlreadyRegistered
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


async def authenticate_doctor(db: AsyncSession, email: str, password: str) -> Doctor | None:
    normalized_email = email.strip().lower()
    result = await db.execute(select(Doctor).where(Doctor.email == normalized_email))
    doctor = result.scalar_one_or_none()
    if doctor is None or not doctor.is_active or not doctor.password_hash:
        verify_password(password, _DUMMY_HASH)
        return None
    return doctor if verify_password(password, doctor.password_hash) else None


async def create_refresh_token(db: AsyncSession, subject_id: int, role: str) -> str:
    """Create and persist a rotating refresh token for a user or doctor."""
    raw = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    record = RefreshToken(
        token_hash=_hash_refresh_token(raw),
        subject_id=subject_id,
        role=role,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(record)
    await db.commit()
    return raw


async def rotate_refresh_token(db: AsyncSession, raw_token: str) -> tuple[str, str, str]:
    """Validate and rotate a refresh token, returning `(access_token, refresh_token, role)`."""
    token_hash = _hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    record = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if (
        record is None
        or record.revoked_at is not None
        or _utc_aware(record.expires_at) <= now
    ):
        raise InvalidRefreshToken

    if record.role == ROLE_DOCTOR:
        doctor = await db.get(Doctor, record.subject_id)
        if doctor is None or not doctor.is_active:
            raise InvalidRefreshToken
    elif record.role == ROLE_USER:
        user = await db.get(User, record.subject_id)
        if user is None:
            raise InvalidRefreshToken
    else:
        raise InvalidRefreshToken

    # Revoke the old token and issue a fresh pair atomically
    record.revoked_at = now
    new_raw = secrets.token_urlsafe(48)
    new_record = RefreshToken(
        token_hash=_hash_refresh_token(new_raw),
        subject_id=record.subject_id,
        role=record.role,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_record)
    await db.commit()

    new_access = create_access_token(record.subject_id, record.role)
    return new_access, new_raw, record.role


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> bool:
    """Revoke a refresh token if it exists and is not yet revoked."""
    token_hash = _hash_refresh_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    record = result.scalar_one_or_none()
    if record is None:
        return False
    if record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return True
