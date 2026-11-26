from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HealthReading(Base):
    __tablename__ = "Health_Readings"

    __table_args__ = (
        UniqueConstraint("device_id", "date_time", name="uq_device_datetime"),
        CheckConstraint("heart_rate_bpm BETWEEN 30 AND 220", name="ck_heart_rate"),
        CheckConstraint("steps >= 0", name="ck_steps"),
        CheckConstraint("calories_kcal >= 0", name="ck_calories"),
        CheckConstraint("spo2_percent BETWEEN 0 AND 100", name="ck_spo2"),
    )

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Devices.device_id"), nullable=False
    )
    date_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heart_rate_bpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    calories_kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    blood_pressure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    spo2_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
