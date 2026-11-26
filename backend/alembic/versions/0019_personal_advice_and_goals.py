"""Personal advice and user goals: User_Goals table

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-26 23:10:00.000000
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS "User_Goals" (
            user_id         INTEGER     PRIMARY KEY REFERENCES "Users"(user_id) ON DELETE CASCADE,
            steps_daily     INTEGER     NOT NULL DEFAULT 10000,
            workouts_weekly INTEGER     NOT NULL DEFAULT 3,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_user_goals_steps_daily CHECK (steps_daily BETWEEN 1000 AND 100000),
            CONSTRAINT ck_user_goals_workouts_weekly CHECK (workouts_weekly BETWEEN 0 AND 14)
        )
    """)

    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "User_Goals" TO app_user;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "User_Goals"')
