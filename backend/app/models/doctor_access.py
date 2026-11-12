from sqlalchemy import Integer, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DoctorAccess(Base):
    __tablename__ = "Doctor_Access"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id"), primary_key=True
    )
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Doctors.doctor_id"), primary_key=True
    )
    access_start: Mapped[object] = mapped_column(Date, nullable=False)
    access_end: Mapped[object] = mapped_column(Date, nullable=False)
