from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.user import User

router = APIRouter()


class Reminder(BaseModel):
    doctor_id: int
    doctor_name: str
    access_end: date
    days_left: int
    priority: Literal["HIGH", "NORMAL"]
    is_read: bool


def due_permissions(user_id: int, today: date):
    return (
        DoctorAccess.user_id == user_id,
        DoctorAccess.access_start <= today,
        DoctorAccess.access_end > today,
        DoctorAccess.access_end <= today + timedelta(days=7),
    )


@router.get("", response_model=list[Reminder])
async def notifications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = await db.scalar(select(func.current_date()))
    rows = await db.execute(
        select(DoctorAccess, Doctor.full_name)
        .join(Doctor, Doctor.doctor_id == DoctorAccess.doctor_id)
        .where(*due_permissions(user.user_id, today))
        .order_by(DoctorAccess.access_end, DoctorAccess.doctor_id)
    )
    items = []
    for access, name in rows:
        days = (access.access_end - today).days
        items.append(Reminder(doctor_id=access.doctor_id, doctor_name=name,
                              access_end=access.access_end, days_left=days,
                              priority="HIGH" if days <= 2 else "NORMAL",
                              is_read=access.reminder_read_for == access.access_end))
    return items


@router.post("/read-all", status_code=204)
async def read_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    today = await db.scalar(select(func.current_date()))
    await db.execute(update(DoctorAccess).where(*due_permissions(user.user_id, today))
                     .values(reminder_read_for=DoctorAccess.access_end))
    await db.commit()


@router.post("/{doctor_id}/{expiry}/read", status_code=204)
async def mark_read(doctor_id: int, expiry: date, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    today = await db.scalar(select(func.current_date()))
    result = await db.execute(
        update(DoctorAccess).where(*due_permissions(user.user_id, today),
                                   DoctorAccess.doctor_id == doctor_id, DoctorAccess.access_end == expiry)
        .values(reminder_read_for=expiry).returning(DoctorAccess.doctor_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Reminder is no longer available.")
    await db.commit()
