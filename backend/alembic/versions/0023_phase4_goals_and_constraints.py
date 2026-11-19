"""Phase 4 — Goals & Constraints: create Goals table and unique index on Devices.serial_number

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-20 00:30:00.000000

Adds:
1. "Goals" table (daily/weekly targets per user & metric with CHECK and UNIQUE constraints).
2. Unique index uq_devices_serial_number on "Devices"(serial_number).
3. Least-privilege DML grants on "Goals" for runtime role `app_user`.
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS "Goals" (
            goal_id      SERIAL PRIMARY KEY,
            user_id      INTEGER          NOT NULL REFERENCES "Users"(user_id) ON DELETE CASCADE,
            period       VARCHAR(20)      NOT NULL,
            metric       VARCHAR(30)      NOT NULL,
            target_value DOUBLE PRECISION NOT NULL,
            created_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
            CONSTRAINT uq_goals_user_period_metric UNIQUE (user_id, period, metric),
            CONSTRAINT ck_goals_period CHECK (period IN ('daily', 'weekly')),
            CONSTRAINT ck_goals_metric CHECK (
                metric IN ('steps', 'calories_kcal', 'distance_km', 'active_minutes', 'workouts')
            ),
            CONSTRAINT ck_goals_target_positive CHECK (target_value > 0)
        )
        """
    )
    op.execute('CREATE INDEX IF NOT EXISTS idx_goals_user_id ON "Goals" (user_id)')
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_serial_number ON "Devices" (serial_number)'
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "Goals" TO "app_user";
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "app_user";
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_devices_serial_number")
    op.execute('DROP TABLE IF EXISTS "Goals"')
