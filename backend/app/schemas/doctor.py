from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DoctorResponse(BaseModel):
    doctor_id: int
    full_name: str
    specialty: Optional[str] = None
    license_number: str

    model_config = ConfigDict(from_attributes=True)


class DoctorAccessResponse(BaseModel):
    user_id: int
    doctor_id: int
    access_start: date
    access_end: date

    model_config = ConfigDict(from_attributes=True)
