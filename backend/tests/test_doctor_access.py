"""
Tests for doctor JWT authentication, role isolation, and patient access control.

Verifies:
1. Active access returns HTTP 200.
2. Expired access returns HTTP 403.
3. Missing access record returns HTTP 403.
4. Boundary dates: access_end == today is inclusive (HTTP 200); access_start == today is inclusive (HTTP 200);
   future access_start (> today) returns HTTP 403.
5. Spoofed HTTP headers (x-doctor-id, x-user-id) cannot authenticate or bypass access checks.
6. User JWT cannot access doctor endpoints (HTTP 403).
7. Doctor JWT cannot access user endpoints (HTTP 403).
8. Doctor cannot access another patient's data without permission.
9. Doctor access is strictly read-only (POST/PUT/PATCH/DELETE not allowed).
10. Access_Log records GRANTED and DENIED attempts with JWT doctor_id and endpoint path.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import ROLE_DOCTOR, ROLE_USER, create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.access_log import AccessLog
from app.models.device import Device
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.health_reading import HealthReading
from app.models.user import User

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    eng = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def test_client(test_engine, test_session_factory):
    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def seed_data(test_session_factory):
    """Create two patients, two doctors, devices, and readings in DB."""
    async with test_session_factory() as session:
        async with session.begin():
            user1 = User(
                full_name="Patient One",
                birth_date=date(1985, 6, 15),
                email="patient1@example.com",
                password_hash=hash_password("PatientPass1"),
            )
            user2 = User(
                full_name="Patient Two",
                birth_date=date(1992, 3, 20),
                email="patient2@example.com",
                password_hash=hash_password("PatientPass2"),
            )
            session.add_all([user1, user2])

            doctor1 = Doctor(
                full_name="Dr. Smith",
                specialty="Cardiology",
                license_number="LIC-001",
                email="smith@example.com",
                password_hash=hash_password("DoctorPass1"),
                is_active=True,
            )
            doctor2 = Doctor(
                full_name="Dr. Adams",
                specialty="Neurology",
                license_number="LIC-002",
                email="adams@example.com",
                password_hash=hash_password("DoctorPass2"),
                is_active=True,
            )
            session.add_all([doctor1, doctor2])
            await session.flush()

            device1 = Device(user_id=user1.user_id, model="FitBand Pro", serial_number="SN-100")
            device2 = Device(user_id=user2.user_id, model="FitBand Pro", serial_number="SN-200")
            session.add_all([device1, device2])
            await session.flush()

            reading1 = HealthReading(
                device_id=device1.device_id,
                date_time=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
                heart_rate_bpm=72,
                steps=5000,
                calories_kcal=200.0,
            )
            reading2 = HealthReading(
                device_id=device2.device_id,
                date_time=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
                heart_rate_bpm=88,
                steps=8000,
                calories_kcal=350.0,
            )
            session.add_all([reading1, reading2])
            await session.flush()

            return {
                "user_id": user1.user_id,
                "other_user_id": user2.user_id,
                "doctor_id": doctor1.doctor_id,
                "other_doctor_id": doctor2.doctor_id,
                "device_id": device1.device_id,
                "doctor_token": create_access_token(doctor1.doctor_id, ROLE_DOCTOR),
                "other_doctor_token": create_access_token(doctor2.doctor_id, ROLE_DOCTOR),
                "user_token": create_access_token(user1.user_id, ROLE_USER),
            }


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_access(session_factory, user_id, doctor_id, start_offset, end_offset):
    today = datetime.now(timezone.utc).date()
    async with session_factory() as session:
        async with session.begin():
            access = DoctorAccess(
                user_id=user_id,
                doctor_id=doctor_id,
                access_start=today + timedelta(days=start_offset),
                access_end=today + timedelta(days=end_offset),
            )
            session.add(access)


@pytest.mark.asyncio
async def test_expired_access_returns_403(test_client, test_session_factory, seed_data):
    """Doctor with access_end in the past must receive HTTP 403."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -10, -1)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_active_access_returns_200(test_client, test_session_factory, seed_data):
    """Doctor with active access must receive HTTP 200 and the patient's readings."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 30)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["heart_rate_bpm"] == 72


@pytest.mark.asyncio
async def test_no_access_record_returns_403(test_client, seed_data):
    """Doctor with no access record at all must receive HTTP 403."""
    ids = seed_data
    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_expired_access_even_without_business_logic_filter(
    test_client, test_session_factory, seed_data
):
    """Expired access_end must always be rejected by the dependency."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -30, -1)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_boundary_dates_end_date_and_start_date_are_inclusive(
    test_client, test_session_factory, seed_data
):
    """access_start <= CURRENT_DATE <= access_end: both start and end days are inclusive."""
    ids = seed_data
    # Ends today (0 offset) -> must still be active (200)
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -7, 0)
    r_end_today = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert r_end_today.status_code == 200

    # Starts today (0 offset) for second patient -> must be active (200)
    await create_access(test_session_factory, ids["other_user_id"], ids["doctor_id"], 0, 7)
    r_start_today = await test_client.get(
        f"/api/v1/doctor/patients/{ids['other_user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert r_start_today.status_code == 200


@pytest.mark.asyncio
async def test_future_access_start_returns_403(test_client, test_session_factory, seed_data):
    """Permission starting tomorrow must not grant access today."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], 1, 10)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_doctor_cannot_access_other_patients_data(
    test_client, test_session_factory, seed_data
):
    """Doctor with access to patient 1 cannot read patient 2's data."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 10)

    r_other = await test_client.get(
        f"/api/v1/doctor/patients/{ids['other_user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert r_other.status_code == 403


@pytest.mark.asyncio
async def test_spoofed_http_headers_cannot_authenticate_or_escalate_access(
    test_client, test_session_factory, seed_data
):
    """x-doctor-id and x-user-id headers must never grant or redirect access."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 10)

    # 1. Legacy headers without Bearer JWT -> 401
    r_no_jwt = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers={
            "x-doctor-id": str(ids["doctor_id"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert r_no_jwt.status_code == 401

    # 2. Doctor 2 (no access) spoofing Doctor 1's ID in x-doctor-id header -> 403
    r_spoof_doc = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers={
            **_bearer(ids["other_doctor_token"]),
            "x-doctor-id": str(ids["doctor_id"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert r_spoof_doc.status_code == 403

    # 3. Doctor 1 requesting patient 2 while spoofing patient 1 in x-user-id header -> 403
    r_spoof_user = await test_client.get(
        f"/api/v1/doctor/patients/{ids['other_user_id']}/readings",
        headers={
            **_bearer(ids["doctor_token"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert r_spoof_user.status_code == 403


@pytest.mark.asyncio
async def test_role_isolation_between_user_and_doctor_tokens(
    test_client, test_session_factory, seed_data
):
    """User JWT cannot open doctor endpoints; doctor JWT cannot open user endpoints."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 10)

    # User token on doctor endpoints -> 403
    r_user_on_doc = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["user_token"]),
    )
    assert r_user_on_doc.status_code == 403

    # Doctor token on user endpoints -> 403
    for path in ("/api/v1/auth/me", "/api/v1/dashboard", "/api/v1/workouts", "/api/v1/sync/devices"):
        r_doc_on_user = await test_client.get(path, headers=_bearer(ids["doctor_token"]))
        assert r_doc_on_user.status_code == 403, f"Expected 403 on {path}, got {r_doc_on_user.status_code}"


@pytest.mark.asyncio
async def test_doctor_access_is_read_only(test_client, test_session_factory, seed_data):
    """Doctor endpoints must not allow mutating patient data."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 10)
    url = f"/api/v1/doctor/patients/{ids['user_id']}/readings"

    for method in ("post", "put", "patch", "delete"):
        fn = getattr(test_client, method)
        r = await fn(url, headers=_bearer(ids["doctor_token"]))
        assert r.status_code == 405

    # Doctor token cannot write readings via /api/v1/sync/reading or /api/v1/sync/batch
    r_sync = await test_client.post(
        "/api/v1/sync/reading",
        headers=_bearer(ids["doctor_token"]),
        json={
            "device_id": ids["device_id"],
            "date_time": "2026-11-19T10:00:00Z",
            "heart_rate_bpm": 70,
        },
    )
    assert r_sync.status_code == 403


@pytest.mark.asyncio
async def test_access_log_records_granted_and_denied_attempts(
    test_client, test_session_factory, seed_data
):
    """Every verified doctor check logs GRANTED or DENIED with JWT doctor_id and endpoint."""
    ids = seed_data
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 10)

    # 1. GRANTED request
    r_ok = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert r_ok.status_code == 200

    # 2. DENIED request (patient 2)
    r_denied = await test_client.get(
        f"/api/v1/doctor/patients/{ids['other_user_id']}/readings",
        headers=_bearer(ids["doctor_token"]),
    )
    assert r_denied.status_code == 403

    async with test_session_factory() as session:
        logs = (
            await session.execute(select(AccessLog).order_by(AccessLog.log_id))
        ).scalars().all()
        assert len(logs) == 2
        assert logs[0].doctor_id == ids["doctor_id"]
        assert logs[0].user_id == ids["user_id"]
        assert logs[0].result == "GRANTED"
        assert logs[0].endpoint == f"/api/v1/doctor/patients/{ids['user_id']}/readings"

        assert logs[1].doctor_id == ids["doctor_id"]
        assert logs[1].user_id == ids["other_user_id"]
        assert logs[1].result == "DENIED"
        assert logs[1].endpoint == f"/api/v1/doctor/patients/{ids['other_user_id']}/readings"
