"""Add partial unique index for active user devices per provider and serial

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-27 00:00:00.000000
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "Devices" TO app_user;
                GRANT USAGE, SELECT ON SEQUENCE "Devices_device_id_seq" TO app_user;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_devices_active_user_provider_serial")
