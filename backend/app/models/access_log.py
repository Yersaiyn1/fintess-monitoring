from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AccessLog(Base):
    __tablename__ = "Access_Log"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Doctors.doctor_id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id"), nullable=False, index=True
    )
    accessed_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
