"""Tests for registration, login and the current-user endpoint."""
from datetime import date, datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import ALGORITHM, ROLE_DOCTOR, decode_access_token, hash_password
from app.models.doctor import Doctor
from app.models.user import User
from scripts.create_doctor import provision_doctor

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
        {"sub": "1", "role": "user", "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
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


# ------------------------------------------------------------------ Doctor Authentication
async def _seed_doctor(
    db_session,
    *,
    full_name: str = "Dr. Elena Petrova",
    specialty: str = "Cardiology",
    license_number: str = "LIC-KZ-001",
    email: str | None = "elena.petrova@example.com",
    password: str | None = "DoctorPass1",
    is_active: bool = True,
) -> Doctor:
    doctor = Doctor(
        full_name=full_name,
        specialty=specialty,
        license_number=license_number,
        email=email,
        password_hash=hash_password(password) if password else None,
        is_active=is_active,
    )
    db_session.add(doctor)
    await db_session.commit()
    await db_session.refresh(doctor)
    return doctor


async def test_doctor_login_success_and_jwt_claims(client, db_session):
    doctor = await _seed_doctor(db_session)
    r = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "  ELENA.Petrova@example.com ", "password": "DoctorPass1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["doctor"]["doctor_id"] == doctor.doctor_id
    assert body["doctor"]["email"] == "elena.petrova@example.com"
    assert body["doctor"]["license_number"] == "LIC-KZ-001"
    assert "password" not in str(body).lower()

    payload = decode_access_token(body["access_token"])
    assert payload.role == ROLE_DOCTOR
    assert payload.subject_id == doctor.doctor_id


async def test_doctor_login_failures_and_unprovisioned_or_inactive(client, db_session):
    await _seed_doctor(db_session)
    await _seed_doctor(
        db_session,
        full_name="Dr. Legacy",
        license_number="LIC-LEGACY",
        email="legacy@example.com",
        password=None,
    )
    await _seed_doctor(
        db_session,
        full_name="Dr. Inactive",
        license_number="LIC-INACTIVE",
        email="inactive@example.com",
        password="DoctorPass1",
        is_active=False,
    )

    wrong_pw = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "elena.petrova@example.com", "password": "WrongPassword1"},
    )
    unknown = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "nobody@example.com", "password": "DoctorPass1"},
    )
    no_pw = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "legacy@example.com", "password": "DoctorPass1"},
    )
    inactive = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "inactive@example.com", "password": "DoctorPass1"},
    )
    assert wrong_pw.status_code == unknown.status_code == no_pw.status_code == inactive.status_code == 401
    assert wrong_pw.json()["detail"] == unknown.json()["detail"]


async def test_no_public_doctor_registration_endpoint(client):
    r = await client.post(
        "/api/v1/auth/doctor/register",
        json={
            "full_name": "Fake Doctor",
            "license_number": "LIC-FAKE",
            "email": "fake@example.com",
            "password": "Password1",
        },
    )
    assert r.status_code in (404, 405)


async def test_doctor_me_and_deactivation_revokes_access(client, db_session):
    doctor = await _seed_doctor(db_session)
    login_res = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "elena.petrova@example.com", "password": "DoctorPass1"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_ok = await client.get("/api/v1/auth/doctor/me", headers=headers)
    assert me_ok.status_code == 200
    assert me_ok.json()["doctor_id"] == doctor.doctor_id

    # User token must not open /auth/doctor/me
    user_token = (await client.post("/api/v1/auth/register", json=REGISTER)).json()["access_token"]
    assert (
        await client.get("/api/v1/auth/doctor/me", headers={"Authorization": f"Bearer {user_token}"})
    ).status_code == 403

    # Deactivating the doctor immediately invalidates existing tokens
    doctor.is_active = False
    await db_session.commit()
    assert (await client.get("/api/v1/auth/doctor/me", headers=headers)).status_code == 401


async def test_provision_doctor_creates_and_updates_existing_legacy_doctor(client, db_session):
    # 1. Existing doctor without email/password
    legacy = Doctor(full_name="Dr. James Chen", specialty="GP", license_number="LIC-KZ-002")
    db_session.add(legacy)
    await db_session.commit()
    legacy_id = legacy.doctor_id

    # Assign credentials to existing doctor by license_number
    updated = await provision_doctor(
        db_session,
        license_number="LIC-KZ-002",
        email="James.Chen@Example.com",
        password="SecurePass9",
    )
    assert updated.doctor_id == legacy_id
    assert updated.email == "james.chen@example.com"

    # Can now log in
    r = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "james.chen@example.com", "password": "SecurePass9"},
    )
    assert r.status_code == 200

    # 2. Duplicate email for another license is rejected
    with pytest.raises(ValueError):
        await provision_doctor(
            db_session,
            license_number="LIC-KZ-999",
            email="james.chen@example.com",
            password="SecurePass9",
            full_name="Another Doctor",
        )

    # 3. Weak password is rejected
    with pytest.raises(ValueError):
        await provision_doctor(
            db_session,
            license_number="LIC-KZ-999",
            email="newdoc@example.com",
            password="weak",
            full_name="New Doctor",
        )
