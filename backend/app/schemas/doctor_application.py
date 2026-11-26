from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class ApplicationDocumentResponse(BaseModel):
    filename: str
    content_type: str
    size: int
    document_id: str


class DoctorApplicationResponse(BaseModel):
    application_id: int
    full_name: str
    email: EmailStr
    specialty: str
    license_number: str
    status: str
    documents: list[ApplicationDocumentResponse]
    submitted_at: datetime
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ApplicationDecision(BaseModel):
    reason: str | None = None
