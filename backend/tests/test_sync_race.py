"""
Tests for device synchronization reliability, transaction atomicity, exception handling,
input validation, device ownership, idempotency, and race condition safety.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import ROLE_USER, create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User
from app.schemas.sync import MAX_SYNC_BATCH_SIZE

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
async def sync_client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def seed_users_and_devices(session_factory):
    """Create two users and their devices for testing."""
    async with session_factory() as session:
        async with session.begin():
            user1 = User(
                full_name="Test User",
                birth_date=date(1990, 1, 1),
                email="test@example.com",
                password_hash=hash_password("Pass1234"),
            )
            user2 = User(
                full_name="Other User",
                birth_date=date(1992, 5, 10),
                email="other@example.com",
                password_hash=hash_password("Pass1234"),
            )
            session.add_all([user1, user2])
            await session.flush()

            device1 = Device(
                user_id=user1.user_id,
                model="FitBand X1",
                serial_number="SN-001",
            )
            device2 = Device(
                user_id=user2.user_id,
                model="FitBand X2",
                serial_number="SN-002",
            )
            session.add_all([device1, device2])
            await session.flush()

            return {
                "user_id": user1.user_id,
                "other_user_id": user2.user_id,
                "device_id": device1.device_id,
                "other_device_id": device2.device_id,
                "user_token": create_access_token(user1.user_id, ROLE_USER),
                "other_user_token": create_access_token(user2.user_id, ROLE_USER),
            }


@pytest_asyncio.fixture(scope="function")
async def seed_device(seed_users_and_devices):
    return seed_users_and_devices["device_id"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


@pytest.mark.asyncio
async def test_idempotent_sync_no_duplicates(
    sync_client, session_factory, seed_users_and_devices
):
    """Syncing the same batch twice via POST /api/v1/sync/batch must not create duplicates."""
    ctx = seed_users_and_devices
    device_id = ctx["device_id"]
    headers = _bearer(ctx["user_token"])
    payload = {
        "device_id": device_id,
        "readings": [
            {
                "device_id": device_id,
                "date_time": r["date_time"].isoformat(),
                "heart_rate_bpm": r["heart_rate_bpm"],
                "steps": r["steps"],
                "calories_kcal": r["calories_kcal"],
                "blood_pressure": r["blood_pressure"],
            }
            for r in SAMPLE_READINGS
        ],
    }

    r1 = await sync_client.post("/api/v1/sync/batch", json=payload, headers=headers)
    assert r1.status_code == 200
    assert r1.json() == {"device_id": device_id, "synced_count": 2, "skipped_count": 0}

    r2 = await sync_client.post("/api/v1/sync/batch", json=payload, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == {"device_id": device_id, "synced_count": 0, "skipped_count": 2}

    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(HealthReading)
                .where(HealthReading.device_id == device_id)
            )
        ).scalar_one()
        device = await session.get(Device, device_id)
        assert device.last_sync_time is not None

    assert count == len(SAMPLE_READINGS)


@pytest.mark.asyncio
async def test_concurrent_sync_no_duplicates(
    sync_client, session_factory, seed_users_and_devices
):
    """Two concurrent POST /api/v1/sync/batch requests with the same batch must not create duplicates."""
    ctx = seed_users_and_devices
    device_id = ctx["device_id"]
    headers = _bearer(ctx["user_token"])
    payload = {
        "device_id": device_id,
        "readings": [
            {
                "date_time": r["date_time"].isoformat(),
                "heart_rate_bpm": r["heart_rate_bpm"],
                "steps": r["steps"],
                "calories_kcal": r["calories_kcal"],
                "blood_pressure": r["blood_pressure"],
            }
            for r in SAMPLE_READINGS
        ],
    }

    res1, res2 = await asyncio.gather(
        sync_client.post("/api/v1/sync/batch", json=payload, headers=headers),
        sync_client.post("/api/v1/sync/batch", json=payload, headers=headers),
    )
    assert res1.status_code == 200 and res2.status_code == 200
    assert res1.json()["synced_count"] + res2.json()["synced_count"] == len(SAMPLE_READINGS)
    assert res1.json()["skipped_count"] + res2.json()["skipped_count"] == len(SAMPLE_READINGS)

    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(HealthReading)
                .where(HealthReading.device_id == device_id)
            )
        ).scalar_one()

    assert count == len(SAMPLE_READINGS)


@pytest.mark.asyncio
async def test_single_reading_sync_and_duplicate_returns_409_without_updating_last_sync_time(
    sync_client, session_factory, seed_users_and_devices
):
    """POST /api/v1/sync/reading inserts and updates last_sync_time; duplicate returns 409 and preserves last_sync_time."""
    ctx = seed_users_and_devices
    device_id = ctx["device_id"]
    headers = _bearer(ctx["user_token"])
    body = {
        "device_id": device_id,
        "date_time": "2025-05-01T12:00:00Z",
        "heart_rate_bpm": 70,
        "steps": 500,
        "calories_kcal": 25.0,
        "blood_pressure": "118/78",
    }

    r1 = await sync_client.post("/api/v1/sync/reading", json=body, headers=headers)
    assert r1.status_code == 201
    assert r1.json()["status"] == "saved"

    # Set a known sentinel last_sync_time in the past to verify a failed duplicate does not overwrite it
    sentinel_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    async with session_factory() as session:
        await session.execute(
            update(Device).where(Device.device_id == device_id).values(last_sync_time=sentinel_time)
        )
        await session.commit()

    # Duplicate timestamp -> 409 Conflict
    r_dup = await sync_client.post("/api/v1/sync/reading", json=body, headers=headers)
    assert r_dup.status_code == 409

    async with session_factory() as session:
        device = await session.get(Device, device_id)
        db_sync_time = (
            device.last_sync_time.replace(tzinfo=timezone.utc)
            if device.last_sync_time.tzinfo is None
            else device.last_sync_time
        )
        assert db_sync_time == sentinel_time


@pytest.mark.asyncio
async def test_single_reading_distinguishes_non_unique_integrity_and_operational_errors(
    sync_client, session_factory, seed_users_and_devices
):
    """Non-unique IntegrityError -> 422; OperationalError -> 503 (never 409, no SQL leaked)."""
    ctx = seed_users_and_devices
    device_id = ctx["device_id"]
    headers = _bearer(ctx["user_token"])
    body = {
        "device_id": device_id,
        "date_time": "2025-05-02T12:00:00Z",
        "heart_rate_bpm": 75,
        "steps": 100,
        "calories_kcal": 10.0,
    }

    # 1. Non-unique IntegrityError (e.g. CHECK constraint failure) -> 422, not 409
    check_err = IntegrityError("INSERT INTO Health_Readings ...", {}, Exception("CHECK constraint failed: ck_steps"))
    with patch.object(AsyncSession, "flush", side_effect=check_err):
        r_integrity = await sync_client.post("/api/v1/sync/reading", json=body, headers=headers)
    assert r_integrity.status_code == 422
    assert "ck_steps" not in r_integrity.text and "INSERT" not in r_integrity.text

    # 2. OperationalError (e.g. database connection lost) -> 503, not 409
    op_err = OperationalError("COMMIT", {}, Exception("server closed the connection unexpectedly"))
    with patch.object(AsyncSession, "commit", side_effect=op_err):
        r_op = await sync_client.post("/api/v1/sync/reading", json=body, headers=headers)
    assert r_op.status_code == 503
    assert "server closed" not in r_op.text


@pytest.mark.asyncio
async def test_single_reading_rolls_back_reading_if_device_update_fails(
    sync_client, session_factory, seed_users_and_devices
):
    """If updating Device.last_sync_time fails after flushing reading, the reading must be rolled back."""
    ctx = seed_users_and_devices
    device_id = ctx["device_id"]
    headers = _bearer(ctx["user_token"])
    body = {
        "device_id": device_id,
        "date_time": "2025-05-03T12:00:00Z",
        "heart_rate_bpm": 80,
        "steps": 250,
        "calories_kcal": 12.0,
    }

    orig_execute = AsyncSession.execute

    async def fail_on_device_update(self, statement, *args, **kwargs):
        if "UPDATE" in str(statement).upper() and "DEVICES" in str(statement).upper():
            raise OperationalError("UPDATE Devices", {}, Exception("simulated update failure"))
        return await orig_execute(self, statement, *args, **kwargs)

    with patch.object(AsyncSession, "execute", new=fail_on_device_update):
        r = await sync_client.post("/api/v1/sync/reading", json=body, headers=headers)
    assert r.status_code == 503

    # Verify reading was rolled back and not left partially saved
    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(HealthReading)
                .where(HealthReading.device_id == device_id)
            )
        ).scalar_one()
        device = await session.get(Device, device_id)
        assert count == 0
        assert device.last_sync_time is None


@pytest.mark.asyncio
async def test_cannot_sync_another_users_device(
    sync_client, session_factory, seed_users_and_devices
):
    """User 1 cannot sync readings or batches to User 2's device."""
    ctx = seed_users_and_devices
    other_device_id = ctx["other_device_id"]
    headers = _bearer(ctx["user_token"])

    r_single = await sync_client.post(
        "/api/v1/sync/reading",
        headers=headers,
        json={
            "device_id": other_device_id,
            "date_time": "2025-05-01T12:00:00Z",
            "heart_rate_bpm": 70,
        },
    )
    assert r_single.status_code == 404

    r_batch = await sync_client.post(
        "/api/v1/sync/batch",
        headers=headers,
        json={
            "device_id": other_device_id,
            "readings": [
                {
                    "date_time": "2025-05-01T12:00:00Z",
                    "heart_rate_bpm": 70,
                }
            ],
        },
    )
    assert r_batch.status_code == 404

    async with session_factory() as session:
        other_dev = await session.get(Device, other_device_id)
        assert other_dev.last_sync_time is None


@pytest.mark.asyncio
async def test_batch_size_limit_and_datetime_and_value_validation(
    sync_client, seed_users_and_devices
):
    """Oversized batches (> 1000), naive datetimes, future datetimes, and invalid values return 422."""
    ctx = seed_users_and_devices
    device_id = ctx["device_id"]
    headers = _bearer(ctx["user_token"])

    # 1. Oversized batch (> MAX_SYNC_BATCH_SIZE)
    base_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    oversized = {
        "device_id": device_id,
        "readings": [
            {
                "date_time": (base_dt + timedelta(minutes=i)).isoformat(),
                "heart_rate_bpm": 70,
            }
            for i in range(MAX_SYNC_BATCH_SIZE + 1)
        ],
    }
    r_big = await sync_client.post("/api/v1/sync/batch", json=oversized, headers=headers)
    assert r_big.status_code == 422

    # 2. Naive datetime (no timezone) -> 422
    r_naive = await sync_client.post(
        "/api/v1/sync/reading",
        headers=headers,
        json={
            "device_id": device_id,
            "date_time": "2024-01-01T10:00:00",
            "heart_rate_bpm": 70,
        },
    )
    assert r_naive.status_code == 422

    # 3. Future datetime -> 422
    future_dt = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r_future = await sync_client.post(
        "/api/v1/sync/reading",
        headers=headers,
        json={
            "device_id": device_id,
            "date_time": future_dt,
            "heart_rate_bpm": 70,
        },
    )
    assert r_future.status_code == 422

    # 4. Out-of-range heart rate (< 30 or > 220) or negative steps -> 422
    r_hr = await sync_client.post(
        "/api/v1/sync/batch",
        headers=headers,
        json={
            "device_id": device_id,
            "readings": [{"date_time": "2024-01-01T10:00:00Z", "heart_rate_bpm": 300}],
        },
    )
    assert r_hr.status_code == 422

    # 5. Timezone with offset (+05:00) is accepted and normalized to UTC
    r_tz = await sync_client.post(
        "/api/v1/sync/reading",
        headers=headers,
        json={
            "device_id": device_id,
            "date_time": "2024-06-01T15:00:00+05:00",
            "heart_rate_bpm": 72,
        },
    )
    assert r_tz.status_code == 201
    # Same instant in UTC ("10:00:00Z") must be detected as duplicate (409)
    r_same_utc = await sync_client.post(
        "/api/v1/sync/reading",
        headers=headers,
        json={
            "device_id": device_id,
            "date_time": "2024-06-01T10:00:00Z",
            "heart_rate_bpm": 72,
        },
    )
    assert r_same_utc.status_code == 409
