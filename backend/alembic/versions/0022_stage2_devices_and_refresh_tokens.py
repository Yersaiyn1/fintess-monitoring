"""Stage 2 — Device API keys & Refresh Tokens

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-20 00:00:00.000000

Adds:
1. Devices.is_active (BOOLEAN NOT NULL DEFAULT TRUE)
2. Devices.api_key_hash (VARCHAR(64), unique partial index uq_devices_api_key_hash)
3. Refresh_Tokens table for rotating/revocable refresh tokens
4. Least-privilege DML grants on Refresh_Tokens for runtime role `app_user`.
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        'ALTER TABLE "Devices" ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE'
    )
    op.execute(
        'ALTER TABLE "Devices" ADD COLUMN IF NOT EXISTS api_key_hash VARCHAR(64)'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_api_key_hash '
        'ON "Devices" (api_key_hash) WHERE api_key_hash IS NOT NULL'
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS "Refresh_Tokens" (
            token_id   SERIAL PRIMARY KEY,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            subject_id INTEGER     NOT NULL,
            role       VARCHAR(20) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS idx_refresh_tokens_subject_role '
        'ON "Refresh_Tokens" (subject_id, role)'
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "Refresh_Tokens" TO "app_user";
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "app_user";
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS "Refresh_Tokens"')
    op.execute("DROP INDEX IF EXISTS uq_devices_api_key_hash")
    op.execute('ALTER TABLE "Devices" DROP COLUMN IF EXISTS api_key_hash')
    op.execute('ALTER TABLE "Devices" DROP COLUMN IF EXISTS is_active')
