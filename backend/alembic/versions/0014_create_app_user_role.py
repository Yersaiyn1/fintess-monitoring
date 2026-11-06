"""Create a low‑privileged role for RLS tests.

Revision ID: 0014
Revises: 0012
Create Date: 2024-02-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create role if it does not exist
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN\n            CREATE ROLE app_user LOGIN PASSWORD 'change_me_please';\n        END IF; END $$;"
    )
    # Grant typical privileges (SELECT, INSERT, UPDATE, DELETE) on relevant tables
    tables = [
        'Users', 'Devices', 'Health_Readings', 'Doctors', 'Doctor_Access', 'Access_Log', 'rls_mismatch_log'
    ]
    for tbl in tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE \"{tbl}\" TO app_user;")
    # Ensure RLS is not bypassed by this role
    op.execute("ALTER ROLE app_user SET row_security = on;")


def downgrade() -> None:
    op.execute("DROP ROLE IF EXISTS app_user;")

