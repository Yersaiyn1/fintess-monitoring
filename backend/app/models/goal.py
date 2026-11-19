from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

GOAL_PERIODS = ("daily", "weekly")
GOAL_METRICS = ("steps", "calories_kcal", "distance_km", "active_minutes", "workouts")


class Goal(Base):
    """User-defined daily or weekly activity goal (Phase 4)."""

    __tablename__ = "Goals"
    __table_args__ = (
        UniqueConstraint("user_id", "period", "metric", name="uq_goals_user_period_metric"),
        CheckConstraint("period IN ('daily','weekly')", name="ck_goals_period"),
        CheckConstraint(
            "metric IN ('steps','calories_kcal','distance_km','active_minutes','workouts')",
            name="ck_goals_metric",
        ),
        CheckConstraint("target_value > 0", name="ck_goals_target_positive"),
    )

    goal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
