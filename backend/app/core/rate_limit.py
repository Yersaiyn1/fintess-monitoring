"""In-memory sliding-window rate limiter for authentication endpoints."""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

MAX_AUTH_ATTEMPTS = 10
WINDOW_SECONDS = 60

_attempts: dict[str, deque[float]] = defaultdict(deque)


def check_auth_rate_limit(key: str) -> None:
    """Enforce at most MAX_AUTH_ATTEMPTS requests per WINDOW_SECONDS for *key*."""
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS
    bucket = _attempts[key]
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= MAX_AUTH_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
    bucket.append(now)


def reset_rate_limiter() -> None:
    """Clear tracked rate-limit attempts (intended for tests)."""
    _attempts.clear()
