"""
Device sync endpoint.

Security & correctness guarantees:
- SELECT ... FOR UPDATE on Devices row prevents parallel-sync races.
- INSERT ... ON CONFLICT (device_id, date_time) DO NOTHING ensures idempotency.
- Both INSERT and UPDATE run in a single DB transaction.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User
from app.schemas.sync import SyncBatchRequest, SyncBatchResponse

logger = logging.getLogger(__name__)
router = APIRouter()


class DeviceCreateRequest(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    serial_number: str = Field(min_length=1, max_length=255)


class DeviceResponse(BaseModel):
    device_id: int
    model: str
    serial_number: str
    last_sync_time: datetime | None = None


class ReadingCreateRequest(BaseModel):
    device_id: int
    date_time: datetime
    heart_rate_bpm: int | None = Field(default=None, ge=30, le=220)
    steps: int | None = Field(default=None, ge=0)
    calories_kcal: float | None = Field(default=None, ge=0)
    blood_pressure: str | None = Field(default=None, max_length=20)


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.user_id == user.user_id).order_by(Device.device_id)
    )
    devices = result.scalars().all()
    return [
        DeviceResponse(
            device_id=d.device_id,
            model=d.model,
            serial_number=d.serial_number,
            last_sync_time=d.last_sync_time,
        )
        for d in devices
    ]


@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def add_device(
    payload: DeviceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = payload.model.strip()
    serial_number = payload.serial_number.strip()
    if not model or not serial_number:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Model and serial number are required.")

    result = await db.execute(
        select(Device).where(
            Device.user_id == user.user_id,
            Device.serial_number == serial_number,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        device = Device(user_id=user.user_id, model=model, serial_number=serial_number)
        db.add(device)
        await db.commit()
        await db.refresh(device)

    return DeviceResponse(
        device_id=device.device_id,
        model=device.model,
        serial_number=device.serial_number,
        last_sync_time=device.last_sync_time,
    )


@router.post("/reading", status_code=status.HTTP_201_CREATED)
async def create_reading(
    payload: ReadingCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(
            Device.device_id == payload.device_id,
            Device.user_id == user.user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found.")

    reading = HealthReading(
        device_id=payload.device_id,
        date_time=payload.date_time,
        heart_rate_bpm=payload.heart_rate_bpm,
        steps=payload.steps,
        calories_kcal=payload.calories_kcal,
        blood_pressure=payload.blood_pressure,
    )
    db.add(reading)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A reading at this time already exists.")
    await db.refresh(reading)
    await db.execute(
        update(Device)
        .where(Device.device_id == payload.device_id)
        .values(last_sync_time=datetime.now(timezone.utc))
    )
    await db.commit()
    return {"reading_id": reading.reading_id, "status": "saved"}


@router.post("/batch", response_model=SyncBatchResponse, status_code=status.HTTP_200_OK)
async def sync_batch(
    payload: SyncBatchRequest,
    user: User = Depends(get_current_user),
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
            .where(
                Device.device_id == payload.device_id,
                Device.user_id == user.user_id,
            )
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

        stmt = (
            pg_insert(HealthReading)
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
