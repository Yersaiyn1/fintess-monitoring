import re
from datetime import date as date_type

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# These rules mirror the Angular validators (frontend/src/app/core/validators/app-validators.ts)
# and the database columns (Users.full_name / Users.email are VARCHAR(255)).
MIN_BIRTH_YEAR = 1900


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    birth_date: date_type
    password: str = Field(..., min_length=8, max_length=64)

    @field_validator("full_name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Full name must not be blank.")
        return v

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("birth_date")
    @classmethod
    def _birth_date_ok(cls, v: date_type) -> date_type:
        if v > date_type.today():
            raise ValueError("Date of birth cannot be in the future.")
        if v.year < MIN_BIRTH_YEAR:
            raise ValueError(f"Year must be {MIN_BIRTH_YEAR} or later.")
        return v

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not (re.search(r"[^\W\d_]", v) and re.search(r"\d", v)):
            raise ValueError("Password must contain at least one letter and one digit.")
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    user_id: int
    full_name: str
    email: str
    birth_date: date_type

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
