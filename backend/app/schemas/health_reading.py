from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthReadingBase(BaseModel):
    device_id: int
    date_time: datetime
    end_time: Optional[datetime] = None
    heart_rate_bpm: Optional[int] = None
    steps: Optional[int] = None
    calories_kcal: Optional[float] = None
    blood_pressure: Optional[str] = None
    spo2_percent: Optional[float] = Field(default=None, ge=0, le=100)


class HealthReadingCreate(HealthReadingBase):
    pass


class HealthReadingResponse(HealthReadingBase):
    reading_id: int

    model_config = ConfigDict(from_attributes=True)
