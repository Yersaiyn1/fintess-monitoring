"""Health Connect improvements: SpO2, Sleep_Sessions, end_time

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-26 00:00:00.000000
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE "Health_Readings"
        ADD COLUMN IF NOT EXISTS spo2_percent DOUBLE PRECISION
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_health_readings_spo2'
            ) THEN
                ALTER TABLE "Health_Readings"
                ADD CONSTRAINT ck_health_readings_spo2 CHECK (spo2_percent BETWEEN 0 AND 100);
            END IF;
        END $$;
    """)
    op.execute("""
        ALTER TABLE "Health_Readings"
        ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_health_readings_end_after_start'
            ) THEN
                ALTER TABLE "Health_Readings"
                ADD CONSTRAINT ck_health_readings_end_after_start
                CHECK (end_time IS NULL OR end_time >= date_time);
            END IF;
        END $$;
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS "Sleep_Sessions" (
            sleep_id   SERIAL PRIMARY KEY,
            device_id  INTEGER     NOT NULL REFERENCES "Devices"(device_id) ON DELETE RESTRICT,
            start_time TIMESTAMPTZ NOT NULL,
            end_time   TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_sleep_sessions_device_start UNIQUE (device_id, start_time),
            CONSTRAINT ck_sleep_sessions_end_after_start CHECK (end_time > start_time)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sleep_sessions_device_start
        ON "Sleep_Sessions" (device_id, start_time)
    """)

    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "Sleep_Sessions" TO app_user;
                GRANT USAGE, SELECT ON SEQUENCE "Sleep_Sessions_sleep_id_seq" TO app_user;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "Sleep_Sessions"')
    op.execute('ALTER TABLE "Health_Readings" DROP CONSTRAINT IF EXISTS ck_health_readings_end_after_start')
    op.execute('ALTER TABLE "Health_Readings" DROP COLUMN IF EXISTS end_time')
    op.execute('ALTER TABLE "Health_Readings" DROP CONSTRAINT IF EXISTS ck_health_readings_spo2')
    op.execute('ALTER TABLE "Health_Readings" DROP COLUMN IF EXISTS spo2_percent')
