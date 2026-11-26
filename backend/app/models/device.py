from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEVICE_PROVIDERS = ("manual", "health_connect", "bluetooth", "fitbit", "garmin", "demo")


class Device(Base):
    __tablename__ = "Devices"

    __table_args__ = (
        CheckConstraint(
            "provider IN ('manual','health_connect','bluetooth','fitbit','garmin','demo')",
            name="ck_devices_provider",
        ),
        Index(
            "uq_devices_active_user_provider_serial",
            "user_id",
            "provider",
            "serial_number",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = TRUE"),
        ),
    )

    device_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_sync_time: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
