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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import get_db
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.schemas.sync import SyncBatchRequest, SyncBatchResponse

logger = logging.getLogger(__name__)
router = APIRouter()


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
