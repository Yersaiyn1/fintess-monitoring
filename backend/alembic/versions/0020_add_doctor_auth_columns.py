"""Stage 1 — Doctor Authentication: add email, password_hash, and is_active to Doctors

Revision ID: 0020
Revises: 0017
Create Date: 2026-11-19 00:00:00.000000

NOTE ON REVISION NUMBERING:
Revisions 0018 and 0019 exist in unmerged local feature branches (feature/device-auth
and feature/doctor-auth). To prevent duplicate revision IDs across branches while
keeping a single linear head on top of 0017, this migration uses revision 0020 with
down_revision = "0017".

All statements are idempotent and non-destructive: existing doctors keep their rows
with email = NULL and password_hash = NULL until credentials are provisioned.
"""
from alembic import op

revision = "0020"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE "Doctors" ADD COLUMN IF NOT EXISTS email VARCHAR(255)')
    op.execute('ALTER TABLE "Doctors" ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)')
    op.execute(
        'ALTER TABLE "Doctors" ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE'
    )
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_doctors_email '
        'ON "Doctors" (email) WHERE email IS NOT NULL'
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_doctors_email")
    op.execute('ALTER TABLE "Doctors" DROP COLUMN IF EXISTS is_active')
    op.execute('ALTER TABLE "Doctors" DROP COLUMN IF EXISTS password_hash')
    op.execute('ALTER TABLE "Doctors" DROP COLUMN IF EXISTS email')
