from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Keep in sync with: migration 0016, schemas/workout.py (WorkoutKind) and services/workouts.py (ACTIVITY_TYPES).
WORKOUT_KINDS = ("Run", "Walk", "Cycling", "Strength", "Yoga")


class Workout(Base):
    """A workout started and stopped by the user (Phase 2). ended_at IS NULL = in progress."""

    __tablename__ = "Workouts"
    __table_args__ = (
        CheckConstraint("kind IN ('Run','Walk','Cycling','Strength','Yoga')", name="ck_workouts_kind"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_workouts_end_after_start"),
        CheckConstraint("steps >= 0", name="ck_workouts_steps"),
        CheckConstraint("distance_km >= 0", name="ck_workouts_distance"),
        CheckConstraint("calories_kcal >= 0", name="ck_workouts_calories"),
        # A user can have only ONE workout in progress (enforced by the database, so it is race-safe).
        Index(
            "uq_workouts_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("ended_at IS NULL"), sqlite_where=text("ended_at IS NULL"),
        ),
    )

    workout_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    distance_km: Mapped[float] = mapped_column(
        Numeric(7, 2, asdecimal=False), nullable=False, default=0, server_default="0"
    )
    calories_kcal: Mapped[float] = mapped_column(
        Numeric(8, 2, asdecimal=False), nullable=False, default=0, server_default="0"
    )
