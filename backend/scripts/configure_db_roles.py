"""Configure and harden the PostgreSQL runtime application role (`APP_DB_USER`).

Separates:
- Migration / Admin role (`DATABASE_MIGRATION_URL` or `DATABASE_URL`): owns tables and runs Alembic.
- Runtime / Application role (`APP_DB_USER` / `APP_DB_PASSWORD`): connects at runtime with
  least-privilege DML permissions and NO schema modification or superuser rights.

Usage (from `backend/`):
    python scripts/configure_db_roles.py
"""
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import INSECURE_DB_PASSWORDS, settings  # noqa: E402

_ROLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_role_and_password(role_name: str, password: str | None) -> tuple[str, str]:
    clean_role = role_name.strip()
    if not _ROLE_RE.match(clean_role):
        raise ValueError(f"Invalid role name: {role_name!r}")
    if not password or not password.strip():
        raise ValueError("APP_DB_PASSWORD must be set in environment or .env.")
    if password in INSECURE_DB_PASSWORDS:
        raise ValueError(
            "APP_DB_PASSWORD must not use the legacy hardcoded password 'change_me_please'."
        )
    if len(password) < 8:
        raise ValueError("APP_DB_PASSWORD must be at least 8 characters long.")
    return clean_role, password


async def configure_runtime_role(
    admin_database_url: str,
    app_user: str,
    app_password: str,
) -> None:
    clean_role, clean_password = validate_role_and_password(app_user, app_password)
    url = make_url(admin_database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("Admin database URL must be a PostgreSQL URL.")

    if url.username == clean_role:
        raise ValueError(
            f"Admin/migration role ({url.username!r}) and runtime role ({clean_role!r}) must be distinct."
        )

    db_name = url.database
    if not db_name or not _ROLE_RE.match(db_name):
        raise ValueError(f"Invalid database name: {db_name!r}")

    conn = await asyncpg.connect(
        host=url.host or "localhost",
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=db_name,
    )
    try:
        quoted = f'"{clean_role}"'
        # Neutralize legacy app_user if different from clean_role
        if clean_role != "app_user":
            await conn.execute(
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

        # Create or update runtime role using format(%I, %L) to safely quote identifier and literal
        await conn.execute(
            """
            SELECT set_config('app.target_role', $1, true),
                   set_config('app.target_pwd',  $2, true);
            """,
            clean_role,
            clean_password,
        )
        await conn.execute(
            """
            DO $$
            DECLARE
                r text := current_setting('app.target_role');
                p text := current_setting('app.target_pwd');
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                    EXECUTE format(
                        'CREATE ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
                        r, p
                    );
                ELSE
                    EXECUTE format(
                        'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS',
                        r, p
                    );
                END IF;
            END
            $$;
            """
        )

        await conn.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO {quoted};')
        await conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC;")
        await conn.execute(f"REVOKE ALL ON SCHEMA public FROM {quoted};")
        await conn.execute(f"GRANT USAGE ON SCHEMA public TO {quoted};")

        await conn.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {quoted};")
        table_grants = [
            ("Users", "SELECT, INSERT, UPDATE"),
            ("Doctors", "SELECT, INSERT, UPDATE"),
            ("Devices", "SELECT, INSERT, UPDATE"),
            ("Health_Readings", "SELECT, INSERT"),
            ("Doctor_Access", "SELECT, INSERT, UPDATE, DELETE"),
            ("Workouts", "SELECT, INSERT, UPDATE"),
            ("Access_Log", "SELECT, INSERT"),
            ("Refresh_Tokens", "SELECT, INSERT, UPDATE, DELETE"),
        ]
        for table_name, privs in table_grants:
            await conn.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = '{table_name}'
                    ) THEN
                        EXECUTE 'GRANT {privs} ON TABLE "{table_name}" TO {quoted}';
                    END IF;
                END
                $$;
                """
            )

        await conn.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted};")
        await conn.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {quoted};"
        )
    finally:
        await conn.close()


def main() -> None:
    app_user = os.environ.get("APP_DB_USER", settings.APP_DB_USER)
    app_password = os.environ.get("APP_DB_PASSWORD", settings.APP_DB_PASSWORD)
    admin_url = os.environ.get("DATABASE_MIGRATION_URL") or settings.migration_database_url
    try:
        asyncio.run(configure_runtime_role(admin_url, app_user, app_password))
        print(f"Configured least-privilege runtime database role '{app_user}'.")
    except Exception as exc:
        print(f"[ERROR] Failed to configure database role: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
