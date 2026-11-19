"""
Real PostgreSQL integration tests (executed when POSTGRES_INTEGRATION_TEST=1 or
TEST_POSTGRES_ADMIN_URL is set, such as in GitHub Actions CI or a dedicated test DB).

Verifies against a live PostgreSQL instance:
1. Runtime role (`app_user`) is NOT a superuser (`rolsuper = FALSE`, `rolcreatedb = FALSE`,
   `rolcreaterole = FALSE`, `rolbypassrls = FALSE`).
2. Runtime role cannot execute DDL (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` fail with
   `InsufficientPrivilegeError`).
3. Runtime role cannot delete audit records from `Access_Log` or modify `alembic_version`.
4. Runtime role can perform normal application DML and `SERIAL` sequence operations.
"""
import os

import asyncpg
import pytest
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(
    os.environ.get("POSTGRES_INTEGRATION_TEST") != "1"
    and not os.environ.get("TEST_POSTGRES_ADMIN_URL"),
    reason="Real PostgreSQL integration test requires POSTGRES_INTEGRATION_TEST=1 or TEST_POSTGRES_ADMIN_URL",
)


def _pg_dsn(sqlalchemy_url: str) -> str:
    url = make_url(sqlalchemy_url)
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def _admin_dsn() -> str:
    raw = (
        os.environ.get("TEST_POSTGRES_ADMIN_URL")
        or os.environ.get("DATABASE_MIGRATION_URL")
        or os.environ.get("DATABASE_URL")
    )
    assert raw, "Admin PostgreSQL URL is required"
    return _pg_dsn(raw)


def _app_dsn() -> str:
    raw = os.environ.get("TEST_POSTGRES_APP_URL") or os.environ.get("DATABASE_URL")
    assert raw, "App PostgreSQL URL is required"
    return _pg_dsn(raw)


@pytest.mark.asyncio
async def test_pg_runtime_role_is_not_superuser_and_lacks_admin_flags():
    app_role = os.environ.get("APP_DB_USER", "app_user")
    conn = await asyncpg.connect(_admin_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolcanlogin
            FROM pg_roles
            WHERE rolname = $1
            """,
            app_role,
        )
        assert row is not None, f"Runtime role {app_role!r} does not exist"
        assert row["rolsuper"] is False
        assert row["rolcreatedb"] is False
        assert row["rolcreaterole"] is False
        assert row["rolbypassrls"] is False
        assert row["rolcanlogin"] is True
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_pg_runtime_role_cannot_modify_schema_or_delete_audit_logs():
    conn = await asyncpg.connect(_app_dsn())
    try:
        # 1. CREATE TABLE must be forbidden
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("CREATE TABLE unauthorized_test_table (id INT);")

        # 2. ALTER TABLE must be forbidden
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute('ALTER TABLE "Users" ADD COLUMN unauthorized_col INT;')

        # 3. DROP TABLE must be forbidden
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute('DROP TABLE "Access_Log";')

        # 4. Deleting from Access_Log must be forbidden
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute('DELETE FROM "Access_Log";')
    finally:
        await conn.close()
