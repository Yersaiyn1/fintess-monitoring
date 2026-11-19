"""Stage 1 — Database Role Hardening: neutralize legacy hardcoded password and enforce least privilege

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-19 00:05:00.000000

Fixes the security vulnerabilities introduced in historical migration 0014 without
modifying 0014 itself:
1. Removes the hardcoded 'change_me_please' credential on `app_user` (either replacing it
   with APP_DB_PASSWORD from the environment or disabling direct password login until
   `scripts/configure_db_roles.py` is run with APP_DB_PASSWORD).
2. Enforces NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS on the runtime role.
3. Revokes CREATE on SCHEMA public from PUBLIC and the runtime role so the runtime role
   cannot execute CREATE TABLE / ALTER TABLE / DROP TABLE.
4. Replaces broad DELETE privileges with table-specific least-privilege DML grants and
   grants USAGE, SELECT on sequences required for SERIAL primary key inserts.
"""
import os
import re

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FORBIDDEN_PASSWORDS = {"change_me_please", "changeme"}


def _validated_role_name(raw: str) -> str:
    name = raw.strip()
    if not _ROLE_RE.match(name):
        raise ValueError(f"Invalid PostgreSQL role identifier: {raw!r}")
    return name


def _harden_role_sql(role_name: str) -> list[str]:
    quoted = f'"{role_name}"'
    return [
        # Ensure role exists without administrative privileges
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role_name}') THEN
                CREATE ROLE {quoted} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            ELSE
                ALTER ROLE {quoted} WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END
        $$;
        """,
        # Prevent non-owners from creating tables/objects in public schema
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC;",
        f"REVOKE ALL ON SCHEMA public FROM {quoted};",
        f"GRANT USAGE ON SCHEMA public TO {quoted};",
        # Reset table privileges and grant only required DML operations
        f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {quoted};",
        f'GRANT SELECT, INSERT, UPDATE ON TABLE "Users" TO {quoted};',
        f'GRANT SELECT, INSERT, UPDATE ON TABLE "Doctors" TO {quoted};',
        f'GRANT SELECT, INSERT, UPDATE ON TABLE "Devices" TO {quoted};',
        f'GRANT SELECT, INSERT ON TABLE "Health_Readings" TO {quoted};',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "Doctor_Access" TO {quoted};',
        f'GRANT SELECT, INSERT, UPDATE ON TABLE "Workouts" TO {quoted};',
        f'GRANT SELECT, INSERT ON TABLE "Access_Log" TO {quoted};',
        # Grant sequence usage so SERIAL columns work for INSERTs
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted};",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {quoted};",
    ]


def upgrade() -> None:
    app_role = _validated_role_name(os.environ.get("APP_DB_USER", "app_user"))
    app_password = os.environ.get("APP_DB_PASSWORD")

    # Always neutralize the hardcoded password on the legacy `app_user` role from 0014
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
                ALTER ROLE "app_user" WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOLOGIN PASSWORD NULL;
            END IF;
        END
        $$;
        """
    )

    for stmt in _harden_role_sql("app_user"):
        op.execute(stmt)

    if app_role != "app_user":
        for stmt in _harden_role_sql(app_role):
            op.execute(stmt)

    if app_password:
        if app_password in _FORBIDDEN_PASSWORDS:
            raise RuntimeError(
                "APP_DB_PASSWORD cannot be set to the compromised legacy password 'change_me_please'."
            )
        conn = op.get_bind()
        conn.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :role_name, :pwd);
                END
                $$;
                """
            ),
            {"role_name": app_role, "pwd": app_password},
        )


def downgrade() -> None:
    # Security hardening of privileges is intentionally non-destructive on downgrade.
    pass
