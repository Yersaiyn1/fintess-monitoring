"""
Device sync endpoint.

Security & correctness guarantees:
- SELECT ... FOR UPDATE on Devices row prevents parallel-sync races.
- INSERT ... ON CONFLICT (device_id, date_time) DO NOTHING ensures idempotency.
- Both INSERT and UPDATE run in a single DB transaction.
"""
import logging
import sqlite3
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User
from app.schemas.sync import HealthConnectUploadResponse, SyncBatchRequest, SyncBatchResponse
from app.services.hc_importer import parse_health_connect_bytes
from app.services.sync import upsert_readings, upsert_sleep_sessions

logger = logging.getLogger(__name__)
router = APIRouter()
HC_BATCH_SIZE = 500


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


@router.post(
    "/upload-hc",
    response_model=HealthConnectUploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_health_connect(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HealthConnectUploadResponse:
    """Import an Android Health Connect export (.zip containing .db, or direct .db)."""
    filename = file.filename or ""
    if not filename.lower().endswith((".zip", ".db")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip and .db files are supported.",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        parsed = parse_health_connect_bytes(raw_bytes, filename=filename)
    except (ValueError, sqlite3.Error, zipfile.BadZipFile) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    result = await db.execute(
        select(Device)
        .where(Device.user_id == current_user.user_id)
        .order_by(Device.device_id.asc())
        .with_for_update()
    )
    device = result.scalars().first()
    if device is None:
        device = Device(
            user_id=current_user.user_id,
            model=parsed.device_model,
            serial_number=f"HC-{current_user.user_id}",
        )
        db.add(device)
        await db.flush()

    total_parsed = len(parsed.readings)
    upsert_res = await upsert_readings(
        db,
        device.device_id,
        parsed.readings,
        batch_size=HC_BATCH_SIZE,
    )
    sleep_count = await upsert_sleep_sessions(
        db,
        device.device_id,
        parsed.sleep_sessions,
        batch_size=HC_BATCH_SIZE,
    )

    device.last_sync_time = datetime.now(timezone.utc)
    await db.commit()

    logger.info(
        "Health Connect import user_id=%s device_id=%s parsed=%s inserted=%s updated=%s unchanged=%s sleep_sessions=%s",
        current_user.user_id,
        device.device_id,
        total_parsed,
        upsert_res.inserted,
        upsert_res.updated,
        upsert_res.unchanged_skipped,
        sleep_count,
    )
    return HealthConnectUploadResponse(
        filename=filename,
        total_parsed=total_parsed,
        inserted=upsert_res.inserted,
        updated=upsert_res.updated,
        unchanged_skipped=upsert_res.unchanged_skipped,
        duplicates_skipped=upsert_res.unchanged_skipped,
        sleep_sessions=sleep_count,
        metrics_breakdown=parsed.metrics_breakdown,
    )
