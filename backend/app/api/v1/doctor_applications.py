"""Public doctor application intake. Uploaded files stay outside the static web root."""
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.doctor_application import DoctorApplication
from app.schemas.doctor_application import DoctorApplicationResponse

router = APIRouter()
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_DOCUMENTS = 5
EMAIL_ADAPTER = TypeAdapter(EmailStr)


def _document_type(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    return None


@router.post("", response_model=DoctorApplicationResponse, status_code=status.HTTP_201_CREATED)
async def submit_doctor_application(
    full_name: str = Form(..., max_length=255),
    email: str = Form(..., max_length=255),
    specialty: str = Form(..., max_length=255),
    license_number: str = Form(..., max_length=100),
    password: str = Form(..., min_length=8, max_length=64),
    documents: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    name = full_name.strip()
    specialty = specialty.strip()
    license_value = license_number.strip()
    if not name or not specialty or not license_value:
        raise HTTPException(422, "Name, specialty and license number are required.")
    try:
        normalized_email = str(EMAIL_ADAPTER.validate_python(email.strip().lower()))
    except ValidationError:
        raise HTTPException(422, "Enter a valid email address.")
    if not (re.search(r"[^\W\d_]", password) and re.search(r"\d", password)):
        raise HTTPException(422, "Password must contain a letter and a digit.")
    if not 1 <= len(documents) <= MAX_DOCUMENTS:
        raise HTTPException(422, f"Upload between 1 and {MAX_DOCUMENTS} verification documents.")

    existing_doctor = await db.execute(select(Doctor.doctor_id).where(
        (func.lower(Doctor.email) == normalized_email) |
        (func.lower(Doctor.license_number) == license_value.lower())
    ).limit(1))
    pending = await db.execute(select(DoctorApplication.application_id).where(
        DoctorApplication.status == "pending",
        (func.lower(DoctorApplication.email) == normalized_email) |
        (func.lower(DoctorApplication.license_number) == license_value.lower()),
    ).limit(1))
    if existing_doctor.scalar_one_or_none() is not None or pending.scalar_one_or_none() is not None:
        raise HTTPException(409, "A doctor account or pending application already uses that email or license number.")

    stored_documents: list[dict] = []
    saved_paths: list[Path] = []
    total_size = 0
    settings.DOCTOR_APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for upload in documents:
            content = await upload.read(MAX_FILE_BYTES + 1)
            if not content or len(content) > MAX_FILE_BYTES:
                raise HTTPException(413, "Each document must be no larger than 10 MB.")
            total_size += len(content)
            if total_size > MAX_TOTAL_BYTES:
                raise HTTPException(413, "All documents together must be no larger than 20 MB.")
            detected = _document_type(content)
            if detected is None:
                raise HTTPException(415, "Documents must be PDF, PNG or JPEG files.")
            content_type, extension = detected
            document_id = uuid4().hex
            stored_name = f"{document_id}{extension}"
            destination = settings.DOCTOR_APPLICATIONS_DIR / stored_name
            destination.write_bytes(content)
            saved_paths.append(destination)
            original_name = Path((upload.filename or "document").replace("\\", "/")).name[:255]
            stored_documents.append({
                "document_id": document_id,
                "stored_name": stored_name,
                "filename": original_name,
                "content_type": content_type,
                "size": len(content),
            })

        application = DoctorApplication(
            full_name=name,
            email=normalized_email,
            specialty=specialty,
            license_number=license_value,
            password_hash=hash_password(password),
            documents=stored_documents,
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)
        return application
    except HTTPException:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise
    except IntegrityError:
        await db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise HTTPException(409, "A pending application already uses that email or license number.")
    except Exception:
        await db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise
