from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class UserGoal(Base):
    """Server-persisted daily step and weekly workout targets for a user."""

    __tablename__ = "User_Goals"

    __table_args__ = (
        CheckConstraint("steps_daily BETWEEN 1000 AND 100000", name="ck_user_goals_steps_daily"),
        CheckConstraint("workouts_weekly BETWEEN 0 AND 14", name="ck_user_goals_workouts_weekly"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), primary_key=True
    )
    steps_daily: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10000, server_default="10000"
    )
    workouts_weekly: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
