"""Administrator-only review of doctor applications and their private documents."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.doctor_application import DoctorApplication
from app.models.user import User
from app.schemas.doctor_application import ApplicationDecision, DoctorApplicationResponse

router = APIRouter()


@router.get("/doctor-applications", response_model=list[DoctorApplicationResponse])
async def list_doctor_applications(
    _: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DoctorApplication).where(DoctorApplication.status == "pending")
        .order_by(DoctorApplication.submitted_at.asc())
    )
    return result.scalars().all()


@router.get("/doctor-applications/{application_id}/documents/{document_id}")
async def get_application_document(
    application_id: int,
    document_id: str,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    application = await db.get(DoctorApplication, application_id)
    metadata = next((doc for doc in (application.documents if application else [])
                     if doc.get("document_id") == document_id), None)
    if metadata is None:
        raise HTTPException(404, "Document not found.")
    path = (settings.DOCTOR_APPLICATIONS_DIR / metadata["stored_name"]).resolve()
    if path.parent != settings.DOCTOR_APPLICATIONS_DIR.resolve() or not path.is_file():
        raise HTTPException(404, "Document file is unavailable.")
    return FileResponse(path, media_type=metadata["content_type"], filename=metadata["filename"])


@router.post("/doctor-applications/{application_id}/approve", response_model=DoctorApplicationResponse)
async def approve_doctor_application(
    application_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    application = await db.get(DoctorApplication, application_id)
    if application is None or application.status != "pending":
        raise HTTPException(404, "Pending application not found.")
    existing = await db.execute(select(Doctor.doctor_id).where(
        (func.lower(Doctor.email) == application.email.lower()) |
        (func.lower(Doctor.license_number) == application.license_number.lower())
    ))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(409, "A doctor account already uses this email or license number.")
    if not application.password_hash:
        raise HTTPException(409, "Application has no password hash; the applicant must reapply.")
    db.add(Doctor(
        full_name=application.full_name,
        email=application.email,
        specialty=application.specialty,
        license_number=application.license_number,
        password_hash=application.password_hash,
    ))
    application.password_hash = None
    application.status = "approved"
    application.reviewed_at = datetime.now(timezone.utc)
    application.reviewed_by_user_id = admin.user_id
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "A doctor account was created concurrently; refresh the application list.")
    await db.refresh(application)
    return application


@router.post("/doctor-applications/{application_id}/reject", response_model=DoctorApplicationResponse)
async def reject_doctor_application(
    application_id: int,
    decision: ApplicationDecision,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    application = await db.get(DoctorApplication, application_id)
    if application is None or application.status != "pending":
        raise HTTPException(404, "Pending application not found.")
    application.status = "rejected"
    application.password_hash = None
    application.reviewed_at = datetime.now(timezone.utc)
    application.reviewed_by_user_id = admin.user_id
    application.rejection_reason = (decision.reason or "").strip()[:1000] or None
    await db.commit()
    await db.refresh(application)
    return application
