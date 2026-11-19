"""Tests for Stage 2 features:
1. Rotating Refresh Tokens & Logout revocation (user & doctor).
2. Rate limiting (HTTP 429 + Retry-After) on authentication endpoints.
3. Patient management of Doctor_Access (directory, grant/update, list, revoke) + live effect.
4. Hardware device API keys (create, rotate, deactivate/activate, dual auth via X-Device-Key).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.rate_limit import MAX_AUTH_ATTEMPTS, reset_rate_limiter
from app.core.security import ROLE_DOCTOR, ROLE_USER, decode_access_token, hash_password
from app.models.doctor import Doctor

REGISTER_USER = {
    "full_name": "Stage Two User",
    "email": "stage2@example.com",
    "birth_date": "1994-06-20",
    "password": "Password123",
}


async def _create_doctor(db_session, *, license_num="LIC-S2-1", email="doc.s2@example.com", active=True):
    doc = Doctor(
        full_name="Dr. Stage Two",
        specialty="Cardiology",
        license_number=license_num,
        email=email,
        password_hash=hash_password("DoctorPass1"),
        is_active=active,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


# ------------------------------------------------------------------ 1. Refresh Tokens & Logout
async def test_user_refresh_token_rotation_and_logout(client):
    reg = await client.post("/api/v1/auth/register", json=REGISTER_USER)
    assert reg.status_code == 201
    refresh_1 = reg.json()["refresh_token"]
    assert refresh_1

    # Rotate refresh token
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["role"] == ROLE_USER
    assert decode_access_token(body["access_token"]).role == ROLE_USER
    refresh_2 = body["refresh_token"]
    assert refresh_2 != refresh_1

    # Reusing the old (already rotated) refresh token must fail -> 401
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert reused.status_code == 401

    # Logout revokes refresh_2
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_2})
    assert out.status_code == 200
    after_logout = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2})
    assert after_logout.status_code == 401


async def test_doctor_refresh_token_and_deactivation_blocks_refresh(client, db_session):
    doc = await _create_doctor(db_session)
    login = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "doc.s2@example.com", "password": "DoctorPass1"},
    )
    assert login.status_code == 200
    refresh_1 = login.json()["refresh_token"]
    assert refresh_1

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_1})
    assert refreshed.status_code == 200
    assert refreshed.json()["role"] == ROLE_DOCTOR
    refresh_2 = refreshed.json()["refresh_token"]

    # Deactivating doctor blocks refreshing with refresh_2
    doc.is_active = False
    await db_session.commit()
    blocked = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_2})
    assert blocked.status_code == 401


# ------------------------------------------------------------------ 2. Auth Rate Limiting
async def test_auth_rate_limiting_returns_429_after_max_attempts(client, db_session):
    reset_rate_limiter()
    await _create_doctor(db_session, license_num="LIC-RL", email="rl.doc@example.com")

    # User login rate limit
    for _ in range(MAX_AUTH_ATTEMPTS):
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "rl.user@example.com", "password": "WrongPassword1"},
        )
        assert r.status_code == 401

    blocked_user = await client.post(
        "/api/v1/auth/login",
        json={"email": "rl.user@example.com", "password": "WrongPassword1"},
    )
    assert blocked_user.status_code == 429
    assert blocked_user.headers.get("retry-after") == "60"

    # Doctor login rate limit (independent key)
    for _ in range(MAX_AUTH_ATTEMPTS):
        r = await client.post(
            "/api/v1/auth/doctor/login",
            json={"email": "rl.doc@example.com", "password": "WrongPassword1"},
        )
        assert r.status_code == 401

    blocked_doc = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "rl.doc@example.com", "password": "WrongPassword1"},
    )
    assert blocked_doc.status_code == 429


# ------------------------------------------------------------------ 3. Doctor Access Management
async def test_patient_grants_updates_lists_and_revokes_doctor_access(client, db_session):
    doc = await _create_doctor(db_session, license_num="LIC-ACC-1", email="acc.doc@example.com")
    reg = await client.post("/api/v1/auth/register", json=REGISTER_USER)
    user_id = reg.json()["user"]["user_id"]
    user_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    doc_login = await client.post(
        "/api/v1/auth/doctor/login",
        json={"email": "acc.doc@example.com", "password": "DoctorPass1"},
    )
    doc_headers = {"Authorization": f"Bearer {doc_login.json()['access_token']}"}

    # 1. Directory returns active doctor
    directory = await client.get("/api/v1/doctor/directory", headers=user_headers)
    assert directory.status_code == 200
    assert any(d["doctor_id"] == doc.doctor_id for d in directory.json())

    # 2. Doctor initially gets 403
    assert (
        await client.get(f"/api/v1/doctor/patients/{user_id}/readings", headers=doc_headers)
    ).status_code == 403

    # 3. Patient grants access (today..+7 days)
    today = datetime.now(timezone.utc).date()
    grant = await client.post(
        "/api/v1/doctor/access",
        headers=user_headers,
        json={
            "doctor_id": doc.doctor_id,
            "access_start": today.isoformat(),
            "access_end": (today + timedelta(days=7)).isoformat(),
        },
    )
    assert grant.status_code == 201
    assert grant.json()["is_active"] is True

    # List access shows the granted permission
    listed = await client.get("/api/v1/doctor/access", headers=user_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1 and listed.json()[0]["doctor_id"] == doc.doctor_id

    # Doctor can now read patient's readings -> 200
    assert (
        await client.get(f"/api/v1/doctor/patients/{user_id}/readings", headers=doc_headers)
    ).status_code == 200

    # 4. Invalid range (end < start) -> 422
    bad_dates = await client.post(
        "/api/v1/doctor/access",
        headers=user_headers,
        json={
            "doctor_id": doc.doctor_id,
            "access_start": today.isoformat(),
            "access_end": (today - timedelta(days=1)).isoformat(),
        },
    )
    assert bad_dates.status_code == 422

    # 5. Patient revokes access -> doctor immediately gets 403
    revoked = await client.delete(f"/api/v1/doctor/access/{doc.doctor_id}", headers=user_headers)
    assert revoked.status_code == 204
    assert (
        await client.get(f"/api/v1/doctor/patients/{user_id}/readings", headers=doc_headers)
    ).status_code == 403


# ------------------------------------------------------------------ 4. Device API Keys & Lifecycle
async def test_device_api_key_auth_rotation_and_deactivation(client):
    reg = await client.post("/api/v1/auth/register", json=REGISTER_USER)
    user_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    # 1. Add device -> returns plain api_key once
    created = await client.post(
        "/api/v1/sync/devices",
        headers=user_headers,
        json={"model": "FitBand Pro", "serial_number": "SN-STAGE2-1"},
    )
    assert created.status_code == 201
    dev = created.json()
    device_id = dev["device_id"]
    key_1 = dev["api_key"]
    assert dev["is_active"] is True
    assert dev["has_key"] is True
    assert key_1

    # 2. Sync single reading using X-Device-Key (no user JWT)
    r_key1 = await client.post(
        "/api/v1/sync/reading",
        headers={"X-Device-Key": key_1},
        json={
            "device_id": device_id,
            "date_time": "2026-11-18T10:00:00Z",
            "heart_rate_bpm": 74,
            "steps": 1200,
        },
    )
    assert r_key1.status_code == 201

    # Wrong X-Device-Key -> 401
    r_bad_key = await client.post(
        "/api/v1/sync/reading",
        headers={"X-Device-Key": "wrong-key"},
        json={"device_id": device_id, "date_time": "2026-11-18T10:05:00Z", "heart_rate_bpm": 74},
    )
    assert r_bad_key.status_code == 401

    # 3. Rotate device key -> key_1 fails (401), key_2 succeeds on /sync/batch
    rotated = await client.post(
        f"/api/v1/sync/devices/{device_id}/rotate-key", headers=user_headers
    )
    assert rotated.status_code == 200
    key_2 = rotated.json()["api_key"]
    assert key_2 and key_2 != key_1

    assert (
        await client.post(
            "/api/v1/sync/reading",
            headers={"X-Device-Key": key_1},
            json={"device_id": device_id, "date_time": "2026-11-18T10:10:00Z", "heart_rate_bpm": 70},
        )
    ).status_code == 401

    r_batch = await client.post(
        "/api/v1/sync/batch",
        headers={"X-Device-Key": key_2},
        json={
            "device_id": device_id,
            "readings": [{"date_time": "2026-11-18T10:15:00Z", "heart_rate_bpm": 76}],
        },
    )
    assert r_batch.status_code == 200 and r_batch.json()["synced_count"] == 1

    # 4. Deactivate device -> both X-Device-Key and user JWT sync return 403
    deact = await client.post(
        f"/api/v1/sync/devices/{device_id}/deactivate", headers=user_headers
    )
    assert deact.status_code == 200 and deact.json()["is_active"] is False

    assert (
        await client.post(
            "/api/v1/sync/reading",
            headers={"X-Device-Key": key_2},
            json={"device_id": device_id, "date_time": "2026-11-18T10:20:00Z", "heart_rate_bpm": 70},
        )
    ).status_code == 403

    assert (
        await client.post(
            "/api/v1/sync/reading",
            headers=user_headers,
            json={"device_id": device_id, "date_time": "2026-11-18T10:20:00Z", "heart_rate_bpm": 70},
        )
    ).status_code == 403

    # 5. Re-activate device -> X-Device-Key works again (201)
    act = await client.post(
        f"/api/v1/sync/devices/{device_id}/activate", headers=user_headers
    )
    assert act.status_code == 200 and act.json()["is_active"] is True

    assert (
        await client.post(
            "/api/v1/sync/reading",
            headers={"X-Device-Key": key_2},
            json={"device_id": device_id, "date_time": "2026-11-18T10:20:00Z", "heart_rate_bpm": 70},
        )
    ).status_code == 201
