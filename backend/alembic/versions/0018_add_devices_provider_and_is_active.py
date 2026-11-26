"""Add Devices.provider and Devices.is_active with provider check and active unique index

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
    op.execute(
        'ALTER TABLE "Devices" ADD COLUMN IF NOT EXISTS provider VARCHAR(32) NOT NULL DEFAULT \'manual\''
    )
    op.execute(
        'ALTER TABLE "Devices" ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE'
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_devices_provider') THEN
                ALTER TABLE "Devices"
                ADD CONSTRAINT ck_devices_provider
                CHECK (provider IN ('manual', 'health_connect', 'bluetooth', 'fitbit', 'garmin', 'demo'));
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_active_user_provider_serial
        ON "Devices" (user_id, provider, serial_number)
        WHERE is_active = TRUE
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "Devices" TO app_user;
                GRANT USAGE, SELECT ON SEQUENCE "Devices_device_id_seq" TO app_user;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_devices_active_user_provider_serial")
    op.execute('ALTER TABLE "Devices" DROP CONSTRAINT IF EXISTS ck_devices_provider')
    op.execute('ALTER TABLE "Devices" DROP COLUMN IF EXISTS provider')
    op.execute('ALTER TABLE "Devices" DROP COLUMN IF EXISTS is_active')
