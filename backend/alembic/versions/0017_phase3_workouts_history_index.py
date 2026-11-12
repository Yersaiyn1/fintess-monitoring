"""Phase 3 — History & Analytics: index for listing / filtering workouts

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-12 00:01:00.000000

History and analytics always filter by user and a date range (and optionally by kind), newest first:
  WHERE user_id = ? [AND kind = ?] AND started_at >= ? AND started_at < ?  ORDER BY started_at DESC
No new tables in this phase. CONCURRENTLY = no table lock on a live database.
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workouts_user_started ON "Workouts" (user_id, started_at DESC)')
        op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_workouts_user_kind_started ON "Workouts" (user_id, kind, started_at DESC)')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_workouts_user_kind_started")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_workouts_user_started")
