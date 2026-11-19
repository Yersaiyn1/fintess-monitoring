"""JWT structure and role separation (Stage 1, task 3.3).

Unit tests for app.core.security plus real HTTP requests against user endpoints.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    ALGORITHM, ROLE_DOCTOR, ROLE_USER, InvalidTokenError, create_access_token, decode_access_token,
)

REGISTER = {"full_name": "Ana", "email": "ana@example.com", "birth_date": "2003-04-15", "password": "abcd1234"}
USER_ENDPOINTS = ["/api/v1/auth/me", "/api/v1/dashboard", "/api/v1/workouts", "/api/v1/analytics/workouts"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sign(payload: dict, key: str | None = None, alg: str = ALGORITHM) -> str:
    return jwt.encode(payload, key or settings.SECRET_KEY, algorithm=alg)


def _claims(**overrides) -> dict:
    base = {"sub": "1", "role": ROLE_USER, "iat": _now(), "exp": _now() + timedelta(minutes=5)}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


async def _register(client) -> tuple[int, str]:
    body = (await client.post("/api/v1/auth/register", json=REGISTER)).json()
    return body["user"]["user_id"], body["access_token"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- unit: token structure
def test_token_contains_sub_role_iat_exp():
    token = create_access_token(42, ROLE_USER)
    raw = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert set(raw) == {"sub", "role", "iat", "exp"}
    assert raw["sub"] == "42" and raw["role"] == "user"
    assert raw["exp"] - raw["iat"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    payload = decode_access_token(token)
    assert payload.subject_id == 42 and payload.role == ROLE_USER
    assert payload.expires_at > payload.issued_at


def test_doctor_token_round_trip():
    payload = decode_access_token(create_access_token(7, ROLE_DOCTOR))
    assert (payload.subject_id, payload.role) == (7, ROLE_DOCTOR)


@pytest.mark.parametrize("role", ["admin", "", "USER", None])
def test_cannot_create_token_with_unknown_role(role):
    with pytest.raises(ValueError):
        create_access_token(1, role)


@pytest.mark.parametrize("sub", [0, -1, True])
def test_cannot_create_token_with_bad_subject(sub):
    with pytest.raises(ValueError):
        create_access_token(sub, ROLE_USER)


@pytest.mark.parametrize(
    "token_factory",
    [
        pytest.param(lambda: _sign(_claims(role=None)), id="missing-role"),
        pytest.param(lambda: _sign(_claims(role="admin")), id="unknown-role"),
        pytest.param(lambda: _sign(_claims(role=["user", "doctor"])), id="role-list"),
        pytest.param(lambda: _sign(_claims(sub=None)), id="missing-sub"),
        pytest.param(lambda: _sign(_claims(sub="abc")), id="non-int-sub"),
        pytest.param(lambda: _sign(_claims(sub="0")), id="zero-sub"),
        pytest.param(lambda: _sign(_claims(sub="-5")), id="negative-sub"),
        pytest.param(lambda: _sign(_claims(iat=None)), id="missing-iat"),
        pytest.param(lambda: _sign(_claims(exp=None)), id="missing-exp"),
        pytest.param(lambda: _sign(_claims(exp=_now() - timedelta(seconds=1))), id="expired"),
        pytest.param(lambda: _sign(_claims(), key="another-secret-key-of-sufficient-length"), id="wrong-key"),
        pytest.param(lambda: _sign(_claims(), alg="HS512"), id="other-alg"),
        pytest.param(lambda: "not.a.jwt", id="garbage"),
        pytest.param(lambda: "", id="empty"),
    ],
)
def test_invalid_tokens_are_rejected(token_factory):
    with pytest.raises(InvalidTokenError):
        decode_access_token(token_factory())


def test_alg_none_token_is_rejected():
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    claims = {"sub": "1", "role": "user", "iat": int(_now().timestamp()), "exp": int(_now().timestamp()) + 300}
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."
    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned)


def test_expected_role_mismatch_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token(create_access_token(1, ROLE_DOCTOR), expected_role=ROLE_USER)


# ---------------------------------------------------------------- HTTP: user endpoints
async def test_login_token_has_user_role(client):
    await client.post("/api/v1/auth/register", json=REGISTER)
    r = await client.post("/api/v1/auth/login", json={"email": REGISTER["email"], "password": REGISTER["password"]})
    payload = decode_access_token(r.json()["access_token"])
    assert payload.role == ROLE_USER and payload.subject_id == r.json()["user"]["user_id"]


@pytest.mark.parametrize("path", USER_ENDPOINTS)
async def test_user_endpoints_accept_user_token(client, path):
    _, token = await _register(client)
    assert (await client.get(path, headers=_bearer(token))).status_code == 200


@pytest.mark.parametrize("path", USER_ENDPOINTS)
async def test_user_endpoints_require_authorization_header(client, path):
    r = await client.get(path)
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("path", USER_ENDPOINTS)
async def test_doctor_token_cannot_open_user_endpoints(client, path):
    user_id, _ = await _register(client)
    # A doctor token whose subject id equals an existing USER id must still be refused.
    doctor_token = create_access_token(user_id, ROLE_DOCTOR)
    assert (await client.get(path, headers=_bearer(doctor_token))).status_code == 403


@pytest.mark.parametrize("path", USER_ENDPOINTS)
async def test_token_without_role_is_401_not_a_fallback(client, path):
    user_id, _ = await _register(client)
    legacy = _sign({"sub": str(user_id), "iat": _now(), "exp": _now() + timedelta(minutes=5)})  # old token format
    assert (await client.get(path, headers=_bearer(legacy))).status_code == 401


async def test_expired_and_invalid_user_tokens_are_401(client):
    user_id, _ = await _register(client)
    expired = _sign(_claims(sub=str(user_id), iat=_now() - timedelta(hours=2), exp=_now() - timedelta(hours=1)))
    forged = _sign(_claims(sub=str(user_id)), key="attacker-chosen-secret-key-0123456789")
    for token in (expired, forged, "garbage"):
        assert (await client.get("/api/v1/auth/me", headers=_bearer(token))).status_code == 401


async def test_non_bearer_scheme_is_401(client):
    _, token = await _register(client)
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Basic {token}"})
    assert r.status_code == 401


async def test_token_of_deleted_or_unknown_user_is_401(client):
    token = create_access_token(999_999, ROLE_USER)
    assert (await client.get("/api/v1/auth/me", headers=_bearer(token))).status_code == 401


async def test_spoofed_identity_headers_are_ignored_for_user_endpoints(client):
    first_id, first_token = await _register(client)
    other = await client.post("/api/v1/auth/register", json={**REGISTER, "email": "bob@example.com"})
    other_id = other.json()["user"]["user_id"]
    r = await client.get(
        "/api/v1/auth/me",
        headers={**_bearer(first_token), "X-User-Id": str(other_id), "X-Doctor-Id": "1"},
    )
    assert r.status_code == 200 and r.json()["user_id"] == first_id
    # Without a token, headers alone never authenticate.
    assert (await client.get("/api/v1/auth/me", headers={"X-User-Id": str(other_id)})).status_code == 401
