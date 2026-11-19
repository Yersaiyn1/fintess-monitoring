"""
Tests for Task 2 (Database Security, Role Separation, Cross-User Data Isolation)
and Task 6 (Database connectivity, disconnect/recovery, migration & role verification).
"""
import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.device import Device
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.health_reading import HealthReading
from scripts.configure_db_roles import configure_runtime_role, validate_role_and_password


async def _register_user(client, email: str, name: str = "User") -> tuple[int, dict[str, str]]:
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": name,
            "email": email,
            "birth_date": "1995-04-10",
            "password": "Password123",
        },
    )
    assert r.status_code == 201
    body = r.json()
    return body["user"]["user_id"], {"Authorization": f"Bearer {body['access_token']}"}


async def test_cross_user_isolation_across_all_user_endpoints(client, db_session):
    """User A cannot view or modify User B's devices, readings, workouts, dashboard, or analytics."""
    uid_a, headers_a = await _register_user(client, "alice.iso@example.com", "Alice")
    uid_b, headers_b = await _register_user(client, "bob.iso@example.com", "Bob")

    # User A creates a device and records a reading + workout
    r_dev_a = await client.post(
        "/api/v1/sync/devices",
        headers=headers_a,
        json={"model": "FitBand Pro", "serial_number": "SN-ALICE-1"},
    )
    assert r_dev_a.status_code == 201
    dev_a_id = r_dev_a.json()["device_id"]

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    r_read_a = await client.post(
        "/api/v1/sync/reading",
        headers=headers_a,
        json={"device_id": dev_a_id, "date_time": now_iso, "heart_rate_bpm": 75, "steps": 4200, "calories_kcal": 180.0},
    )
    assert r_read_a.status_code == 201

    r_start = await client.post("/api/v1/workouts/start", headers=headers_a, json={"kind": "Run"})
    assert r_start.status_code == 201
    workout_a_id = r_start.json()["id"]

    # 1. User B cannot see User A's devices
    r_devs_b = await client.get("/api/v1/sync/devices", headers=headers_b)
    assert r_devs_b.status_code == 200
    assert r_devs_b.json() == []

    # 2. User B cannot stop or view User A's workout
    assert (await client.post(f"/api/v1/workouts/{workout_a_id}/stop", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/workouts/{workout_a_id}", headers=headers_b)).status_code == 404

    # Stop workout as User A
    assert (await client.post(f"/api/v1/workouts/{workout_a_id}/stop", headers=headers_a)).status_code == 200

    # 3. User B's dashboard and analytics do not include User A's steps or workouts
    dash_b = (await client.get("/api/v1/dashboard", headers=headers_b)).json()
    assert dash_b["user_id"] == uid_b
    assert sum(day["steps"] for day in dash_b["week"]) == 0

    analytics_b = (await client.get("/api/v1/analytics/workouts?period=week", headers=headers_b)).json()
    assert analytics_b["totals"]["workouts"] == 0

    # 4. Spoofing X-User-Id header as User A while authenticated as User B does not leak User A's data
    spoof_headers = {**headers_b, "X-User-Id": str(uid_a)}
    dash_spoof = (await client.get("/api/v1/dashboard", headers=spoof_headers)).json()
    assert dash_spoof["user_id"] == uid_b
    assert sum(day["steps"] for day in dash_spoof["week"]) == 0


async def test_doctor_patients_list_shows_only_patients_with_active_permission(client, db_session):
    """GET /api/v1/doctor/patients returns only patients with active permission for the logged-in doctor."""
    from app.core.security import ROLE_DOCTOR, create_access_token, hash_password

    uid_active, _ = await _register_user(client, "p.active@example.com", "Active Patient")
    uid_expired, _ = await _register_user(client, "p.expired@example.com", "Expired Patient")
    uid_none, _ = await _register_user(client, "p.none@example.com", "Unlinked Patient")

    doc = Doctor(
        full_name="Dr. Verify",
        specialty="Cardiology",
        license_number="LIC-VER-1",
        email="verify.doc@example.com",
        password_hash=hash_password("DocPass123"),
        is_active=True,
    )
    db_session.add(doc)
    await db_session.flush()

    today = datetime.now(timezone.utc).date()
    db_session.add_all(
        [
            DoctorAccess(
                user_id=uid_active,
                doctor_id=doc.doctor_id,
                access_start=today - timedelta(days=5),
                access_end=today,  # ends today -> inclusive!
            ),
            DoctorAccess(
                user_id=uid_expired,
                doctor_id=doc.doctor_id,
                access_start=today - timedelta(days=20),
                access_end=today - timedelta(days=1),
            ),
        ]
    )
    await db_session.commit()

    doc_headers = {"Authorization": f"Bearer {create_access_token(doc.doctor_id, ROLE_DOCTOR)}"}
    r = await client.get("/api/v1/doctor/patients", headers=doc_headers)
    assert r.status_code == 200
    patients = r.json()
    assert [p["user_id"] for p in patients] == [uid_active]


async def test_health_endpoints_and_db_disconnect_recovery(client):
    """/health and /health/db report status and recover cleanly after a transient DB outage."""
    r_live = await client.get("/health")
    assert r_live.status_code == 200
    assert r_live.json() == {"status": "ok"}

    # Simulate DB outage on /health/db -> 503
    with patch("app.main.AsyncSessionLocal") as mock_session_cls:
        mock_cm = mock_session_cls.return_value.__aenter__.return_value
        mock_cm.execute.side_effect = OperationalError("SELECT 1", {}, Exception("connection refused"))
        r_down = await client.get("/health/db")
        assert r_down.status_code == 503

    # Simulate recovery -> 200
    with patch("app.main.AsyncSessionLocal") as mock_session_cls:
        mock_cm = mock_session_cls.return_value.__aenter__.return_value
        mock_cm.execute.return_value = None
        r_up = await client.get("/health/db")
        assert r_up.status_code == 200
        assert r_up.json() == {"status": "ok", "database": "up"}


def test_role_and_password_validation_rejects_hardcoded_and_weak_credentials():
    """Role configuration rejects 'change_me_please', short passwords, invalid identifiers, and identical admin/app roles."""
    with pytest.raises(ValueError, match="change_me_please"):
        validate_role_and_password("app_user", "change_me_please")

    with pytest.raises(ValueError):
        validate_role_and_password("app_user", "")

    with pytest.raises(ValueError):
        validate_role_and_password("app_user", "short")

    with pytest.raises(ValueError):
        validate_role_and_password("invalid-role-name; DROP ROLE postgres;", "ValidPassword123")


@pytest.mark.asyncio
async def test_configure_runtime_role_forbids_using_admin_role_as_runtime_role():
    with pytest.raises(ValueError, match="must be distinct"):
        await configure_runtime_role(
            "postgresql+asyncpg://postgres:StrongAdminPass1@localhost:5432/fitness",
            "postgres",
            "StrongAppPass1",
        )


def test_production_settings_reject_compromised_db_password(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a-very-long-production-secret-key-with-over-32-chars")
    monkeypatch.setenv("APP_DB_PASSWORD", "change_me_please")

    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="change_me_please"):
            get_settings()
    finally:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("APP_DB_PASSWORD", raising=False)
        get_settings.cache_clear()
