from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def ensure_utc_datetime(v: datetime) -> datetime:
    """Require a timezone-aware datetime not in the future and normalize it to UTC."""
    if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
        raise ValueError("date_time must be timezone-aware (include UTC 'Z' or timezone offset).")
    utc_dt = v.astimezone(timezone.utc)
    if utc_dt > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("date_time cannot be in the future.")
    return utc_dt


class HealthReadingBase(BaseModel):
    device_id: Optional[int] = Field(default=None, ge=1)
    date_time: datetime
    heart_rate_bpm: Optional[int] = Field(default=None, ge=30, le=220)
    steps: Optional[int] = Field(default=None, ge=0)
    calories_kcal: Optional[float] = Field(default=None, ge=0)
    blood_pressure: Optional[str] = Field(default=None, max_length=20)


class HealthReadingCreate(HealthReadingBase):
    @field_validator("date_time")
    @classmethod
    def _validate_date_time(cls, v: datetime) -> datetime:
        return ensure_utc_datetime(v)


class HealthReadingResponse(HealthReadingBase):
    reading_id: int
    device_id: int

    model_config = ConfigDict(from_attributes=True)

    @field_validator("date_time")
    @classmethod
    def _normalize_output_dt(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
