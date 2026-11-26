from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthReadingBase(BaseModel):
    device_id: Optional[int] = None
    date_time: datetime
    heart_rate_bpm: Optional[int] = Field(default=None, ge=30, le=220)
    steps: Optional[int] = Field(default=None, ge=0)
    calories_kcal: Optional[float] = Field(default=None, ge=0)
    blood_pressure: Optional[str] = Field(default=None, max_length=20)


class HealthReadingCreate(HealthReadingBase):
    pass


class HealthReadingResponse(HealthReadingBase):
    reading_id: int
    device_id: int

    model_config = ConfigDict(from_attributes=True)
