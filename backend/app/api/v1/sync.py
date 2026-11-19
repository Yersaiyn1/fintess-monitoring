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

logger = logging.getLogger(__name__)
router = APIRouter()
HC_BATCH_SIZE = 500


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

    inserted = 0
    total_parsed = len(parsed.readings)
    if parsed.readings:
        for i in range(0, total_parsed, HC_BATCH_SIZE):
            batch = [
                {
                    "device_id": device.device_id,
                    "date_time": reading["date_time"],
                    "heart_rate_bpm": reading["heart_rate_bpm"],
                    "steps": reading["steps"],
                    "calories_kcal": reading["calories_kcal"],
                    "blood_pressure": reading["blood_pressure"],
                }
                for reading in parsed.readings[i : i + HC_BATCH_SIZE]
            ]
            stmt = (
                pg_insert(HealthReading)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["device_id", "date_time"])
            )
            res = await db.execute(stmt)
            if res.rowcount and res.rowcount > 0:
                inserted += res.rowcount

    device.last_sync_time = datetime.now(timezone.utc)
    await db.commit()

    duplicates_skipped = max(0, total_parsed - inserted)
    logger.info(
        "Health Connect import user_id=%s device_id=%s parsed=%s inserted=%s skipped=%s",
        current_user.user_id,
        device.device_id,
        total_parsed,
        inserted,
        duplicates_skipped,
    )
    return HealthConnectUploadResponse(
        filename=filename,
        total_parsed=total_parsed,
        inserted=inserted,
        duplicates_skipped=duplicates_skipped,
        metrics_breakdown=parsed.metrics_breakdown,
    )
