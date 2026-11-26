from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class DoctorResponse(BaseModel):
    doctor_id: int
    full_name: str
    specialty: Optional[str] = None
    license_number: str

    model_config = ConfigDict(from_attributes=True)


class DoctorLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class DoctorIdentityResponse(BaseModel):
    doctor_id: int
    full_name: str
    specialty: Optional[str] = None
    email: EmailStr
    license_number: str

    model_config = ConfigDict(from_attributes=True)


class DoctorTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    doctor: DoctorIdentityResponse


class DoctorAccessResponse(BaseModel):
    user_id: int
    doctor_id: int
    access_start: date
    access_end: date

    model_config = ConfigDict(from_attributes=True)
