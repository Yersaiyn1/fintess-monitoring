from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Doctor(Base):
    __tablename__ = "Doctors"

    doctor_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialty: Mapped[object] = mapped_column(String(255), nullable=True)
    license_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
