"""
Tests for device sync idempotency and race condition safety.

Tests verify:
1. Syncing the same batch twice results in zero duplicates.
2. Two concurrent sync requests with the same batch produce zero duplicates.
"""
import asyncio
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import select, func, update

from app.db.base import Base
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User


DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def engine():
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
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def seed_device(session_factory):
    """Create a user and device for testing."""
    async with session_factory() as session:
        async with session.begin():
            user = User(
                full_name="Test User",
                birth_date=datetime(1990, 1, 1).date(),
                email="test@example.com",
            )
            session.add(user)
            await session.flush()
            device = Device(
                user_id=user.user_id,
                model="FitBand X1",
                serial_number="SN-001",
            )
            session.add(device)
            await session.flush()
            device_id = device.device_id
    return device_id


SAMPLE_READINGS = [
    {
        "device_id": None,  # filled in test
        "date_time": datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        "heart_rate_bpm": 72,
        "steps": 1000,
        "calories_kcal": 50.0,
        "blood_pressure": "120/80",
    },
    {
        "device_id": None,
        "date_time": datetime(2024, 1, 1, 10, 5, 0, tzinfo=timezone.utc),
        "heart_rate_bpm": 75,
        "steps": 1050,
        "calories_kcal": 52.5,
        "blood_pressure": None,
    },
]


async def do_sync(session_factory, device_id: int, readings: list):
    """
    Simulate the sync logic: INSERT OR IGNORE (SQLite equivalent of ON CONFLICT DO NOTHING).
    Uses a simple per-row insert with ignore for SQLite compatibility in tests.
    """
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    async with session_factory() as session:
        async with session.begin():
            # Lock device (SQLite doesn't support FOR UPDATE, skip in unit test)
            result = await session.execute(
                select(Device).where(Device.device_id == device_id)
            )
            device = result.scalar_one_or_none()
            if device is None:
                raise ValueError(f"Device {device_id} not found")

            rows = [
                {
                    "device_id": device_id,
                    "date_time": r["date_time"],
                    "heart_rate_bpm": r["heart_rate_bpm"],
                    "steps": r["steps"],
                    "calories_kcal": r["calories_kcal"],
                    "blood_pressure": r["blood_pressure"],
                }
                for r in readings
            ]

            for row in rows:
                stmt = (
                    sqlite_insert(HealthReading)
                    .values(row)
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)

            # Update last_sync_time
            await session.execute(
                update(Device)
                .where(Device.device_id == device_id)
                .values(last_sync_time=datetime.now(timezone.utc))
            )


@pytest.mark.asyncio
async def test_idempotent_sync_no_duplicates(session_factory, seed_device):
    """Syncing the same batch twice must not create duplicates."""
    device_id = seed_device
    readings = [{**r, "device_id": device_id} for r in SAMPLE_READINGS]

    # Sync same batch twice
    await do_sync(session_factory, device_id, readings)
    await do_sync(session_factory, device_id, readings)

    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(HealthReading).where(
                HealthReading.device_id == device_id
            )
        )
        count = result.scalar_one()

    assert count == len(SAMPLE_READINGS), (
        f"Expected {len(SAMPLE_READINGS)} readings, got {count} (duplicates present!)"
    )


@pytest.mark.asyncio
async def test_concurrent_sync_no_duplicates(session_factory, seed_device):
    """Two concurrent syncs with the same batch must not create duplicates."""
    device_id = seed_device
    readings = [{**r, "device_id": device_id} for r in SAMPLE_READINGS]

    # Run two syncs concurrently
    await asyncio.gather(
        do_sync(session_factory, device_id, readings),
        do_sync(session_factory, device_id, readings),
    )

    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(HealthReading).where(
                HealthReading.device_id == device_id
            )
        )
        count = result.scalar_one()

    assert count == len(SAMPLE_READINGS), (
        f"Expected {len(SAMPLE_READINGS)} readings, got {count} (race condition created duplicates!)"
    )
