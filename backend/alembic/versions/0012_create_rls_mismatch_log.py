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
    op.create_table(
        "rls_mismatch_log",
        sa.Column("log_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("endpoint", sa.String(256), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column("rows_mismatched", sa.Integer(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
    )
    # Index for fast aggregation by timestamp.
    op.create_index("ix_rls_mismatch_timestamp", "rls_mismatch_log", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_rls_mismatch_timestamp", table_name="rls_mismatch_log")
    op.drop_table("rls_mismatch_log")

