"""Phase 1 — Authentication: add Users.password_hash

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-05 00:00:00.000000

Nullable on purpose: existing users (e.g. from the old seed) have no password yet and
simply cannot log in until one is set. New accounts always get a bcrypt hash.
Safe to run on a live table (adding a nullable column is instant) and idempotent.
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "Users" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)')


def downgrade() -> None:
    op.execute('ALTER TABLE "Users" DROP COLUMN IF EXISTS password_hash')
