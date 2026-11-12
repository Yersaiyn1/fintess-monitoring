"""Phase 2 — Activity Tracking: create Workouts

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-12 00:00:00.000000

A workout is started (ended_at IS NULL) and later stopped (ended_at, steps, distance, calories filled in).
The partial unique index guarantees ONE workout in progress per user, even with parallel requests.
New table = instant and safe on a live database; statements are re-runnable.
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Workouts" (
            workout_id    SERIAL PRIMARY KEY,
            user_id       INTEGER      NOT NULL REFERENCES "Users"(user_id) ON DELETE CASCADE,
            kind          VARCHAR(20)  NOT NULL,
            started_at    TIMESTAMPTZ  NOT NULL,
            ended_at      TIMESTAMPTZ,
            steps         INTEGER      NOT NULL DEFAULT 0,
            distance_km   NUMERIC(7,2) NOT NULL DEFAULT 0,
            calories_kcal NUMERIC(8,2) NOT NULL DEFAULT 0,
            CONSTRAINT ck_workouts_kind CHECK (kind IN ('Run','Walk','Cycling','Strength','Yoga')),
            CONSTRAINT ck_workouts_end_after_start CHECK (ended_at IS NULL OR ended_at >= started_at),
            CONSTRAINT ck_workouts_steps CHECK (steps >= 0),
            CONSTRAINT ck_workouts_distance CHECK (distance_km >= 0),
            CONSTRAINT ck_workouts_calories CHECK (calories_kcal >= 0)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_workouts_one_active_per_user
        ON "Workouts" (user_id) WHERE ended_at IS NULL
    """)


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "Workouts"')
