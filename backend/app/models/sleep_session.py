from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SleepSession(Base):
    """Sleep interval recorded by a device (e.g. Health Connect sleep_session_record_table)."""

    __tablename__ = "Sleep_Sessions"

    __table_args__ = (
        UniqueConstraint("device_id", "start_time", name="uq_sleep_sessions_device_start"),
        CheckConstraint("end_time > start_time", name="ck_sleep_sessions_end_after_start"),
        Index("idx_sleep_sessions_device_start", "device_id", "start_time"),
    )

    sleep_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Devices.device_id", ondelete="RESTRICT"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
