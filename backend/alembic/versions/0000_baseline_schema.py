"""Baseline schema: the core tables (Users, Doctors, Devices, Health_Readings, Doctor_Access)

Revision ID: 0000
Revises:
Create Date: 2024-01-01 00:00:00.000000

WHY THIS EXISTS
Migrations 0001+ assume the tables already exist, so `alembic upgrade head` failed on an
empty database. This baseline creates them.  Every statement uses IF NOT EXISTS, so it is
also safe on a database that was created earlier from database/schema.sql.

Alembic is the single source of truth for the schema. database/schema.sql is a readable
snapshot of the same result (kept in sync, see docs/ADDING_A_PHASE.md).
"""
from alembic import op

revision = "0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Users" (
            user_id           SERIAL PRIMARY KEY,
            full_name         VARCHAR(255) NOT NULL,
            birth_date        DATE         NOT NULL,
            email             VARCHAR(255) NOT NULL UNIQUE,
            registration_date DATE         NOT NULL DEFAULT CURRENT_DATE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Doctors" (
            doctor_id      SERIAL PRIMARY KEY,
            full_name      VARCHAR(255) NOT NULL,
            specialty      VARCHAR(255),
            license_number VARCHAR(100) NOT NULL UNIQUE
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Devices" (
            device_id      SERIAL PRIMARY KEY,
            user_id        INTEGER      NOT NULL REFERENCES "Users"(user_id) ON DELETE RESTRICT,
            model          VARCHAR(255) NOT NULL,
            serial_number  VARCHAR(255) NOT NULL,
            last_sync_time TIMESTAMPTZ
        )
    """)
    # The UNIQUE(device_id, date_time) rule is added by migration 0001 (production-safe, CONCURRENTLY).
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Health_Readings" (
            reading_id     SERIAL PRIMARY KEY,
            device_id      INTEGER      NOT NULL REFERENCES "Devices"(device_id) ON DELETE RESTRICT,
            date_time      TIMESTAMPTZ  NOT NULL,
            heart_rate_bpm INTEGER      CHECK (heart_rate_bpm BETWEEN 30 AND 220),
            steps          INTEGER      CHECK (steps >= 0),
            calories_kcal  NUMERIC(8,2) CHECK (calories_kcal >= 0),
            blood_pressure VARCHAR(20)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Doctor_Access" (
            user_id      INTEGER NOT NULL REFERENCES "Users"(user_id)     ON DELETE CASCADE,
            doctor_id    INTEGER NOT NULL REFERENCES "Doctors"(doctor_id) ON DELETE CASCADE,
            access_start DATE    NOT NULL,
            access_end   DATE    NOT NULL,
            CONSTRAINT pk_doctor_access PRIMARY KEY (user_id, doctor_id),
            CONSTRAINT chk_doctor_access_dates CHECK (access_end >= access_start)
        )
    """)


def downgrade() -> None:
    # Dropping the core tables would destroy all data: intentionally not supported.
    raise NotImplementedError("The baseline cannot be downgraded.")
