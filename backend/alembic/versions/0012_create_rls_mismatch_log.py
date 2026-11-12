"""Create rls_mismatch_log table for shadow‑check logging.

Revision ID: 0012
Revises: 0003
Create Date: 2024-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Table stores mismatches observed when RLS is not enforced.
    op.execute("""
        CREATE TABLE IF NOT EXISTS rls_mismatch_log (
            log_id          SERIAL PRIMARY KEY,
            timestamp       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            endpoint        VARCHAR(256) NOT NULL,
            user_id         INTEGER,
            doctor_id       INTEGER,
            rows_mismatched INTEGER      NOT NULL,
            details         TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_rls_mismatch_timestamp ON rls_mismatch_log (timestamp)")


def downgrade() -> None:
    op.drop_index("ix_rls_mismatch_timestamp", table_name="rls_mismatch_log")
    op.drop_table("rls_mismatch_log")

