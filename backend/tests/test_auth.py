"""Tests for registration, login and the current-user endpoint."""
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.security import ALGORITHM
from app.models.user import User

REGISTER = {
    "full_name": "Ana Test",
    "email": "Ana@Example.com",
    "birth_date": "2003-04-15",
    "password": "abcd1234",
}


async def test_register_returns_token_and_never_stores_plain_password(client, db_session):
    r = await client.post("/api/v1/auth/register", json=REGISTER)
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["email"] == "ana@example.com"  # normalised to lower case
    assert "password" not in str(body).lower().replace("password_hash", "")

    user = (await db_session.execute(select(User).where(User.email == "ana@example.com"))).scalar_one()
    assert user.password_hash and user.password_hash != REGISTER["password"]
    assert user.password_hash.startswith("$2")  # bcrypt


async def test_register_duplicate_email_is_rejected_case_insensitive(client):
    assert (await client.post("/api/v1/auth/register", json=REGISTER)).status_code == 201
    r = await client.post("/api/v1/auth/register", json={**REGISTER, "email": "ana@example.com"})
    assert r.status_code == 409


async def test_register_validation(client):
    weak = await client.post("/api/v1/auth/register", json={**REGISTER, "password": "onlyletters"})
    short = await client.post("/api/v1/auth/register", json={**REGISTER, "password": "a1"})
    future = await client.post("/api/v1/auth/register", json={**REGISTER, "birth_date": "2999-01-01"})
    bad_email = await client.post("/api/v1/auth/register", json={**REGISTER, "email": "nope"})
    blank = await client.post("/api/v1/auth/register", json={**REGISTER, "full_name": "   "})
    assert [x.status_code for x in (weak, short, future, bad_email, blank)] == [422] * 5


async def test_login_success_and_failures(client):
    await client.post("/api/v1/auth/register", json=REGISTER)
    ok = await client.post("/api/v1/auth/login", json={"email": " ANA@example.com ", "password": "abcd1234"})
    assert ok.status_code == 200 and ok.json()["access_token"]

    wrong = await client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "wrong"})
    unknown = await client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "abcd1234"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # does not reveal which emails exist


async def test_user_without_password_cannot_login(client, db_session):
    from datetime import date
    db_session.add(User(full_name="Old User", email="old@example.com", birth_date=date(1990, 1, 1)))
    await db_session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": "old@example.com", "password": "anything1"})
    assert r.status_code == 401


async def test_me_requires_a_valid_token(client):
    token = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["access_token"]

    ok = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.json()["full_name"] == "Ana Test"

    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})).status_code == 401

    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.SECRET_KEY, algorithm=ALGORITHM,
    )
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})).status_code == 401


async def test_cors_allows_the_angular_dev_server(client):
    r = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,authorization"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:4200"
