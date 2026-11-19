from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DoctorLoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return v.strip().lower()


class DoctorResponse(BaseModel):
    doctor_id: int
    full_name: str
    specialty: Optional[str] = None
    license_number: str
    email: Optional[str] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class DoctorTokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    doctor: DoctorResponse


class DoctorAccessResponse(BaseModel):
    user_id: int
    doctor_id: int
    access_start: date
    access_end: date

    model_config = ConfigDict(from_attributes=True)


class DoctorAccessGrantRequest(BaseModel):
    doctor_id: int = Field(..., ge=1)
    access_start: date
    access_end: date

    @model_validator(mode="after")
    def _validate_dates(self) -> "DoctorAccessGrantRequest":
        if self.access_end < self.access_start:
            raise ValueError("access_end must not be earlier than access_start.")
        return self


class DoctorAccessDetailResponse(BaseModel):
    user_id: int
    doctor_id: int
    doctor_name: str
    specialty: Optional[str] = None
    license_number: str
    access_start: date
    access_end: date
    is_active: bool
