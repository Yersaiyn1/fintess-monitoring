"""
Tests for doctor access control.

Verifies that:
1. A doctor with expired access_end gets HTTP 403.
2. A doctor with active access gets HTTP 200.
3. A doctor with no access record gets HTTP 403.
"""
import pytest
import pytest_asyncio
from datetime import date, timedelta, datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.device import Device
from app.models.health_reading import HealthReading


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
    """Create user, doctor, device, and readings in DB."""
    async with test_session_factory() as session:
        async with session.begin():
            user = User(
                full_name="Patient One",
                birth_date=date(1985, 6, 15),
                email="patient@example.com",
            )
            session.add(user)

            doctor = Doctor(
                full_name="Dr. Smith",
                specialty="Cardiology",
                license_number="LIC-001",
            )
            session.add(doctor)
            await session.flush()

            device = Device(
                user_id=user.user_id,
                model="FitBand Pro",
                serial_number="SN-100",
            )
            session.add(device)
            await session.flush()

            reading = HealthReading(
                device_id=device.device_id,
                date_time=datetime(2024, 6, 1, 12, 0, 0),
                heart_rate_bpm=72,
                steps=5000,
                calories_kcal=200.0,
            )
            session.add(reading)
            await session.flush()

            return {
                "user_id": user.user_id,
                "doctor_id": doctor.doctor_id,
                "device_id": device.device_id,
            }


async def create_access(session_factory, user_id, doctor_id, start_offset, end_offset):
    today = date.today()
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
    # Create access that ended yesterday
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -10, -1)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers={
            "x-doctor-id": str(ids["doctor_id"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert response.status_code == 403, (
        f"Expected 403 for expired access, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_active_access_returns_200(test_client, test_session_factory, seed_data):
    """Doctor with active access must receive HTTP 200."""
    ids = seed_data
    # Create access active today
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -5, 30)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers={
            "x-doctor-id": str(ids["doctor_id"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 for active access, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_no_access_record_returns_403(test_client, seed_data):
    """Doctor with no access record at all must receive HTTP 403."""
    ids = seed_data
    # No DoctorAccess record created

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers={
            "x-doctor-id": str(ids["doctor_id"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_expired_access_even_without_business_logic_filter(test_client, test_session_factory, seed_data):
    """
    Critical: even if endpoint code doesn't explicitly filter access_end,
    the dependency must still reject expired doctors.
    access_end expired → must return 403.
    """
    ids = seed_data
    # Expired access
    await create_access(test_session_factory, ids["user_id"], ids["doctor_id"], -30, -1)

    response = await test_client.get(
        f"/api/v1/doctor/patients/{ids['user_id']}/readings",
        headers={
            "x-doctor-id": str(ids["doctor_id"]),
            "x-user-id": str(ids["user_id"]),
        },
    )
    assert response.status_code == 403, (
        "CRITICAL: Expired doctor access was not blocked by dependency!"
    )
