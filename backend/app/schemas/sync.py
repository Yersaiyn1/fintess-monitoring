from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.health_reading import HealthReadingCreate

DeviceProvider = Literal["manual", "health_connect", "bluetooth", "fitbit", "garmin", "demo"]


class DeviceCreateRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=255)
    serial_number: str = Field(..., min_length=1, max_length=255)
    provider: DeviceProvider = "manual"

    @field_validator("model", "serial_number")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Must not be blank.")
        return cleaned


class DeviceEnsureRequest(BaseModel):
    provider: DeviceProvider
    name: str = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Device name must not be blank.")
        return cleaned[:255]


class DeviceResponse(BaseModel):
    device_id: int
    user_id: int
    model: str
    serial_number: str
    provider: DeviceProvider
    is_active: bool
    last_sync_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SyncBatchRequest(BaseModel):
    device_id: int
    readings: List[HealthReadingCreate]


class SyncBatchResponse(BaseModel):
    device_id: int
    synced_count: int
    skipped_count: int
