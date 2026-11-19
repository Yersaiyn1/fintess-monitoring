"""Password hashing and JWT helpers (no database access here).

JWT structure (HS256, signed with settings.SECRET_KEY):
    sub   str  subject id (Users.user_id or Doctors.doctor_id, depending on role)
    role  str  "user" | "doctor"  (REQUIRED: a token without a known role is invalid)
    iat   int  issued at (unix time, UTC)
    exp   int  expires at (unix time, UTC)

All four claims are mandatory. A token is accepted only if it is correctly signed, not expired,
carries a known role and a positive integer subject. Role checks for a particular endpoint are done
by the FastAPI dependencies in app/api/deps.py (get_current_user / get_current_doctor).
"""
import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"

ROLE_USER = "user"
ROLE_DOCTOR = "doctor"
ROLES = frozenset({ROLE_USER, ROLE_DOCTOR})

_REQUIRED_CLAIMS = ["sub", "role", "iat", "exp"]


# ---------------------------------------------------------------- passwords
def _prehash(password: str) -> bytes:
    # bcrypt only looks at the first 72 BYTES; hashing first makes every character count
    # (important for long or non-ASCII passwords).
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except ValueError:
        return False


# ---------------------------------------------------------------- JWT
class InvalidTokenError(Exception):
    """The token is malformed, badly signed, expired or has invalid claims."""


@dataclass(frozen=True)
class TokenPayload:
    subject_id: int
    role: str
    issued_at: datetime
    expires_at: datetime


def create_access_token(subject_id: int, role: str, expires_delta: timedelta | None = None) -> str:
    """Create a signed access token for a user or a doctor."""
    if role not in ROLES:
        raise ValueError(f"Unknown token role: {role!r}")
    if not isinstance(subject_id, int) or isinstance(subject_id, bool) or subject_id <= 0:
        raise ValueError("subject_id must be a positive integer")
    now = datetime.now(timezone.utc)
    lifetime = expires_delta if expires_delta is not None else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(subject_id),
        "role": role,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str, expected_role: str | None = None) -> TokenPayload:
    """Validate a token and return its claims.

    Raises InvalidTokenError for: bad signature, other algorithm (incl. "none"), expired token,
    missing claims, unknown role, non-integer subject, or (if given) a role other than expected_role.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": _REQUIRED_CLAIMS, "verify_exp": True, "verify_iat": True},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    role = payload.get("role")
    if not isinstance(role, str) or role not in ROLES:
        raise InvalidTokenError("Unknown or missing role claim.")

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.isdigit():
        raise InvalidTokenError("Subject must be a positive integer.")
    subject_id = int(sub)
    if subject_id <= 0:
        raise InvalidTokenError("Subject must be a positive integer.")

    if expected_role is not None and role != expected_role:
        raise InvalidTokenError(f"Token role {role!r} is not allowed here.")

    try:
        issued_at = datetime.fromtimestamp(int(payload["iat"]), tz=timezone.utc)
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InvalidTokenError("Invalid iat/exp claim.") from exc

    return TokenPayload(subject_id=subject_id, role=role, issued_at=issued_at, expires_at=expires_at)
