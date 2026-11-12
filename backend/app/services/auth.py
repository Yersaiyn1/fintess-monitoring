"""Authentication business logic (used by api/v1/auth.py)."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest

# Used to spend the same time on "unknown email" as on "wrong password".
_DUMMY_HASH = hash_password("dummy-password-1")


class EmailAlreadyRegistered(Exception):
    pass


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
