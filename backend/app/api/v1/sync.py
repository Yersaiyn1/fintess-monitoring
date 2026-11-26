"""
Device sync and registration endpoints.

Security & correctness guarantees:
- SELECT ... FOR UPDATE on Devices row prevents parallel-sync races.
- INSERT ... ON CONFLICT (device_id, date_time) DO NOTHING ensures idempotency.
- Both INSERT and UPDATE run in a single DB transaction.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User
from app.schemas.sync import (
    DeviceCreateRequest,
    DeviceEnsureRequest,
    DeviceResponse,
    SyncBatchRequest,
    SyncBatchResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_PROVIDER_SERIAL_PREFIX: dict[str, str] = {
    "bluetooth": "BLE",
    "demo": "DEMO",
    "health_connect": "HEALTH_CONNECT",
    "manual": "MANUAL",
    "fitbit": "FITBIT",
    "garmin": "GARMIN",
}


def _build_ensure_serial(provider: str, user_id: int) -> str:
    prefix = _PROVIDER_SERIAL_PREFIX.get(provider, provider.upper())
    return f"{prefix}-{user_id}".upper()


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return active devices owned by the authenticated user."""
    result = await db.execute(
        select(Device)
        .where(Device.user_id == user.user_id, Device.is_active.is_(True))
        .order_by(Device.device_id.asc())
    )
    return list(result.scalars().all())


@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new device for the authenticated user."""
    device = Device(
        user_id=user.user_id,
        model=payload.model,
        serial_number=payload.serial_number,
        provider=payload.provider,
        is_active=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.post("/devices/ensure", response_model=DeviceResponse, status_code=status.HTTP_200_OK)
async def ensure_device(
    payload: DeviceEnsureRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Idempotently return or create the user's active device for a given provider."""
    serial_number = _build_ensure_serial(payload.provider, user.user_id)
    stmt = (
        select(Device)
        .where(
            Device.user_id == user.user_id,
            Device.provider == payload.provider,
            Device.serial_number == serial_number,
            Device.is_active.is_(True),
        )
        .with_for_update()
    )

    device = (await db.execute(stmt)).scalar_one_or_none()
    if device is not None:
        return device

    dialect_name = (await db.connection()).dialect.name
    insert_fn = sqlite_insert if dialect_name == "sqlite" else pg_insert
    active_where = text("is_active = 1") if dialect_name == "sqlite" else text("is_active = TRUE")
    insert_stmt = (
        insert_fn(Device)
        .values(
            user_id=user.user_id,
            model=payload.name,
            serial_number=serial_number,
            provider=payload.provider,
            is_active=True,
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "provider", "serial_number"],
            index_where=active_where,
        )
    )
    await db.execute(insert_stmt)
    await db.commit()
    return (await db.execute(stmt)).scalar_one()


@router.post("/batch", response_model=SyncBatchResponse, status_code=status.HTTP_200_OK)
async def sync_batch(
    payload: SyncBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Sync a batch of Health_Readings for a device.

    Idempotent: re-sending the same batch is safe (duplicates are silently skipped).
    Race-safe: concurrent syncs for the same device_id are serialized via FOR UPDATE.
    """
    async with db.begin():
        # 1. Lock the device row to serialize concurrent syncs
        result = await db.execute(
            select(Device)
            .where(Device.device_id == payload.device_id)
            .with_for_update()
        )
        device = result.scalar_one_or_none()
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device {payload.device_id} not found.",
            )

        # 2. Build INSERT ... ON CONFLICT DO NOTHING for each reading
        if not payload.readings:
            return SyncBatchResponse(
                device_id=payload.device_id, synced_count=0, skipped_count=0
            )

        rows = [
            {
                "device_id": payload.device_id,
                "date_time": r.date_time,
                "heart_rate_bpm": r.heart_rate_bpm,
                "steps": r.steps,
                "calories_kcal": r.calories_kcal,
                "blood_pressure": r.blood_pressure,
            }
            for r in payload.readings
        ]

        dialect_name = (await db.connection()).dialect.name
        insert_fn = sqlite_insert if dialect_name == "sqlite" else pg_insert
        stmt = (
            insert_fn(HealthReading)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["device_id", "date_time"])
        )
        result = await db.execute(stmt)
        # rowcount is the number of actually inserted rows
        synced_count = result.rowcount if result.rowcount >= 0 else 0
        skipped_count = len(payload.readings) - synced_count

        # 3. Update last_sync_time on the device
        now_utc = datetime.now(timezone.utc)
        await db.execute(
            update(Device)
            .where(Device.device_id == payload.device_id)
            .values(last_sync_time=now_utc)
        )

    logger.info(
        "Sync complete for device_id=%s: synced=%s skipped=%s",
        payload.device_id,
        synced_count,
        skipped_count,
    )
    return SyncBatchResponse(
        device_id=payload.device_id,
        synced_count=synced_count,
        skipped_count=skipped_count,
    )
