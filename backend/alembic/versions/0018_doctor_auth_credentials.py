"""Add provisioned credentials for doctor login.

Revision ID: 0018
Revises: 0017
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "Doctors" ADD COLUMN IF NOT EXISTS email VARCHAR(255)')
    op.execute('ALTER TABLE "Doctors" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)')
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_doctors_email_lower ON "Doctors" (lower(email)) WHERE email IS NOT NULL')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS uq_doctors_email_lower')
    op.execute('ALTER TABLE "Doctors" DROP COLUMN IF EXISTS password_hash')
    op.execute('ALTER TABLE "Doctors" DROP COLUMN IF EXISTS email')
