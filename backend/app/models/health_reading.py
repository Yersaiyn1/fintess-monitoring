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
    )

    reading_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Devices.device_id"), nullable=False
    )
    date_time: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    heart_rate_bpm: Mapped[object] = mapped_column(Integer, nullable=True)
    steps: Mapped[object] = mapped_column(Integer, nullable=True)
    calories_kcal: Mapped[object] = mapped_column(Float, nullable=True)
    blood_pressure: Mapped[object] = mapped_column(String(20), nullable=True)
