"""
Device sync endpoints (`/api/v1/sync`).

Security & correctness guarantees:
- Device management endpoints require an authenticated user (`get_current_user`) and verify device ownership.
- Sync endpoints (`POST /reading` and `POST /batch`) support dual authentication:
  1) Hardware band auth via `X-Device-Key` header (constant-time SHA-256 hash verification), OR
  2) Authenticated user via `Authorization: Bearer <role="user" JWT>` owning the device.
- Deactivated devices (`is_active == False`) cannot sync readings (`HTTP 403`).
- `SELECT ... FOR UPDATE` on the `Devices` row serializes concurrent syncs for the same device.
- `POST /reading` atomically inserts the reading and updates `Device.last_sync_time` in a single
  transaction, distinguishing unique constraint violations (409) from other integrity errors (422)
  and database connectivity/operational errors (503).
- `POST /batch` enforces a maximum batch size (1000), timezone-aware UTC timestamps, value bounds,
  and `INSERT ... ON CONFLICT (device_id, date_time) DO NOTHING` in a single atomic transaction.
"""
import hashlib
import hmac
import logging
import secrets
import sqlite3
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, InterfaceError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User
from app.schemas.health_reading import ensure_utc_datetime
from app.schemas.sync import HealthConnectUploadResponse, SyncBatchRequest, SyncBatchResponse
from app.services.hc_importer import parse_health_connect_bytes

logger = logging.getLogger(__name__)
router = APIRouter()
HC_BATCH_SIZE = 500

_bearer_optional = HTTPBearer(auto_error=False)


def generate_device_key() -> str:
    """Generate a high-entropy URL-safe device API key."""
    return secrets.token_urlsafe(32)


def hash_device_key(plain_key: str) -> str:
    """Compute the SHA-256 hex digest of a device API key."""
    return hashlib.sha256(plain_key.encode("utf-8")).hexdigest()


def verify_device_key(plain_key: str, stored_hash: str | None) -> bool:
    """Constant-time verification of a device API key against its stored hash."""
    if not stored_hash or not plain_key:
        return False
    return hmac.compare_digest(hash_device_key(plain_key), stored_hash)


class DeviceCreateRequest(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    serial_number: str = Field(min_length=1, max_length=255)


class DeviceResponse(BaseModel):
    device_id: int
    model: str
    serial_number: str
    is_active: bool = True
    has_key: bool = False
    api_key: str | None = None
    last_sync_time: datetime | None = None


class ReadingCreateRequest(BaseModel):
    device_id: int = Field(..., ge=1)
    date_time: datetime
    heart_rate_bpm: int | None = Field(default=None, ge=30, le=220)
    steps: int | None = Field(default=None, ge=0)
    calories_kcal: float | None = Field(default=None, ge=0)
    blood_pressure: str | None = Field(default=None, max_length=20)

    @field_validator("date_time")
    @classmethod
    def _validate_date_time(cls, v: datetime) -> datetime:
        return ensure_utc_datetime(v)


def _device_to_response(device: Device, api_key: str | None = None) -> DeviceResponse:
    return DeviceResponse(
        device_id=device.device_id,
        model=device.model,
        serial_number=device.serial_number,
        is_active=device.is_active,
        has_key=device.api_key_hash is not None,
        api_key=api_key,
        last_sync_time=device.last_sync_time,
    )


def _is_unique_violation(exc: IntegrityError) -> bool:
    """Return True if *exc* was caused by a UNIQUE constraint / unique index violation."""
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if pgcode == "23505":
        return True
    msg = str(orig or exc).lower()
    return (
        "unique constraint" in msg
        or "unique violation" in msg
        or "uq_device_datetime" in msg
        or "uq_health_readings_device_datetime" in msg
        or "duplicate key" in msg
    )


def _dialect_insert(db: AsyncSession):
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "sqlite":
        return sqlite_insert
    return pg_insert


async def _resolve_sync_device(
    db: AsyncSession,
    device_id: int,
    credentials: HTTPAuthorizationCredentials | None,
    x_device_key: str | None,
) -> Device:
    """Authenticate either via `X-Device-Key` or user JWT, lock the device row, and check `is_active`."""
    if x_device_key:
        result = await db.execute(
            select(Device).where(Device.device_id == device_id).with_for_update()
        )
        device = result.scalar_one_or_none()
        if device is None or not verify_device_key(x_device_key, device.api_key_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid device API key.",
            )
        if not device.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device is deactivated.",
            )
        return device

    user = await get_current_user(credentials, db)
    result = await db.execute(
        select(Device)
        .where(
            Device.device_id == device_id,
            Device.user_id == user.user_id,
        )
        .with_for_update()
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Device {device_id} not found.")
    if not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device is deactivated.",
        )
    return device


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.user_id == user.user_id).order_by(Device.device_id)
    )
    return [_device_to_response(d) for d in result.scalars().all()]


@router.post("/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def add_device(
    payload: DeviceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    model = payload.model.strip()
    serial_number = payload.serial_number.strip()
    if not model or not serial_number:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Model and serial number are required."
        )

    result = await db.execute(
        select(Device).where(
            Device.user_id == user.user_id,
            Device.serial_number == serial_number,
        )
    )
    device = result.scalar_one_or_none()
    plain_key: str | None = None
    if device is None:
        plain_key = generate_device_key()
        device = Device(
            user_id=user.user_id,
            model=model,
            serial_number=serial_number,
            is_active=True,
            api_key_hash=hash_device_key(plain_key),
        )
        db.add(device)
        await db.commit()
        await db.refresh(device)

    return _device_to_response(device, api_key=plain_key)


@router.post("/devices/{device_id}/rotate-key", response_model=DeviceResponse)
async def rotate_device_key(
    device_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rotate the API key for an owned device (immediately invalidating the previous key)."""
    device = (
        await db.execute(
            select(Device).where(
                Device.device_id == device_id,
                Device.user_id == user.user_id,
            )
        )
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found.")

    plain_key = generate_device_key()
    device.api_key_hash = hash_device_key(plain_key)
    await db.commit()
    await db.refresh(device)
    return _device_to_response(device, api_key=plain_key)


@router.post("/devices/{device_id}/deactivate", response_model=DeviceResponse)
async def deactivate_device(
    device_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an owned device so it cannot sync new readings."""
    device = (
        await db.execute(
            select(Device).where(
                Device.device_id == device_id,
                Device.user_id == user.user_id,
            )
        )
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found.")

    device.is_active = False
    await db.commit()
    await db.refresh(device)
    return _device_to_response(device)


@router.post("/devices/{device_id}/activate", response_model=DeviceResponse)
async def activate_device(
    device_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-activate a previously deactivated device."""
    device = (
        await db.execute(
            select(Device).where(
                Device.device_id == device_id,
                Device.user_id == user.user_id,
            )
        )
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found.")

    device.is_active = True
    await db.commit()
    await db.refresh(device)
    return _device_to_response(device)


@router.post("/reading", status_code=status.HTTP_201_CREATED)
async def create_reading(
    payload: ReadingCreateRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Save a single reading and update Device.last_sync_time atomically in one transaction."""
    try:
        device = await _resolve_sync_device(db, payload.device_id, credentials, x_device_key)

        reading = HealthReading(
            device_id=device.device_id,
            date_time=payload.date_time,
            heart_rate_bpm=payload.heart_rate_bpm,
            steps=payload.steps,
            calories_kcal=payload.calories_kcal,
            blood_pressure=payload.blood_pressure,
        )
        db.add(reading)
        await db.flush()

        now_utc = datetime.now(timezone.utc)
        await db.execute(
            update(Device)
            .where(Device.device_id == device.device_id)
            .values(last_sync_time=now_utc)
        )
        reading_id = reading.reading_id
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        if _is_unique_violation(exc):
            logger.info(
                "Duplicate reading rejected for device_id=%s date_time=%s",
                payload.device_id,
                payload.date_time,
            )
            raise HTTPException(
                status.HTTP_409_CONFLICT, "A reading at this time already exists."
            )
        logger.warning(
            "Integrity constraint violation while saving reading for device_id=%s: %s",
            payload.device_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Reading violates data integrity constraints.",
        )
    except (OperationalError, InterfaceError, DBAPIError, OSError) as exc:
        await db.rollback()
        logger.exception(
            "Database connection/operational error while saving reading for device_id=%s: %s",
            payload.device_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Database is temporarily unavailable.",
        )
    except Exception as exc:
        await db.rollback()
        logger.exception(
            "Unexpected error while saving reading for device_id=%s: %s",
            payload.device_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to save reading.",
        )

    return {"reading_id": reading_id, "status": "saved"}


@router.post("/batch", response_model=SyncBatchResponse, status_code=status.HTTP_200_OK)
async def sync_batch(
    payload: SyncBatchRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    x_device_key: str | None = Header(default=None, alias="X-Device-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync a batch of Health_Readings for a device owned by the user or authenticated via X-Device-Key.

    Idempotent: re-sending the same batch is safe (duplicates are silently skipped).
    Race-safe: concurrent syncs for the same device_id are serialized via FOR UPDATE.
    Atomic: readings insert and Device.last_sync_time update commit or roll back together.
    """
    try:
        device = await _resolve_sync_device(db, payload.device_id, credentials, x_device_key)

        if not payload.readings:
            await db.rollback()
            return SyncBatchResponse(
                device_id=payload.device_id, synced_count=0, skipped_count=0
            )

        rows = [
            {
                "device_id": device.device_id,
                "date_time": r.date_time,
                "heart_rate_bpm": r.heart_rate_bpm,
                "steps": r.steps,
                "calories_kcal": r.calories_kcal,
                "blood_pressure": r.blood_pressure,
            }
            for r in payload.readings
        ]

        insert_fn = _dialect_insert(db)
        stmt = (
            insert_fn(HealthReading)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["device_id", "date_time"])
        )
        insert_result = await db.execute(stmt)
        synced_count = (
            insert_result.rowcount
            if insert_result.rowcount is not None and insert_result.rowcount >= 0
            else 0
        )
        skipped_count = len(payload.readings) - synced_count

        now_utc = datetime.now(timezone.utc)
        await db.execute(
            update(Device)
            .where(Device.device_id == device.device_id)
            .values(last_sync_time=now_utc)
        )
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Integrity constraint violation during batch sync for device_id=%s: %s",
            payload.device_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Batch contains readings that violate data integrity constraints.",
        )
    except (OperationalError, InterfaceError, DBAPIError, OSError) as exc:
        await db.rollback()
        logger.exception(
            "Database operational error during batch sync for device_id=%s: %s",
            payload.device_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Database is temporarily unavailable.",
        )
    except Exception as exc:
        await db.rollback()
        logger.exception(
            "Unexpected error during batch sync for device_id=%s: %s",
            payload.device_id,
            exc,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Failed to synchronize readings batch.",
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
        .order_by(Device.is_active.desc(), Device.device_id.asc())
        .with_for_update()
    )
    device = result.scalars().first()
    if device is None:
        device = Device(
            user_id=current_user.user_id,
            model=parsed.device_model,
            serial_number=f"HC-{current_user.user_id}",
            is_active=True,
        )
        db.add(device)
        await db.flush()

    inserted = 0
    total_parsed = len(parsed.readings)
    if parsed.readings:
        insert_fn = _dialect_insert(db)
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
                insert_fn(HealthReading)
                .values(batch)
                .on_conflict_do_nothing(index_elements=["device_id", "date_time"])
            )
            res = await db.execute(stmt)
            if res.rowcount is not None and res.rowcount > 0:
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
