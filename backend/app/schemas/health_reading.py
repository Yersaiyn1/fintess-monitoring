from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class HealthReadingBase(BaseModel):
    device_id: int
    date_time: datetime
    heart_rate_bpm: Optional[int] = None
    steps: Optional[int] = None
    calories_kcal: Optional[float] = None
    blood_pressure: Optional[str] = None


class HealthReadingCreate(HealthReadingBase):
    pass


class HealthReadingResponse(HealthReadingBase):
    reading_id: int

    model_config = ConfigDict(from_attributes=True)
