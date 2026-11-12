"""One-command database setup (works on Windows, macOS, Linux; no `psql` needed).

    python scripts/setup_db.py            # create the database if missing + apply all migrations
    python scripts/setup_db.py --seed     # ... and load the demo data (re-runnable)

It uses DATABASE_URL from .env, so every teammate keeps their own PostgreSQL password locally
and only the "recipe" (migrations + seed.sql) is stored in git.
"""
import argparse
import asyncio
import re
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SEED_FILE = BACKEND_DIR.parent / "database" / "seed.sql"
sys.path.insert(0, str(BACKEND_DIR))

import asyncpg  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402


def fail(message: str) -> None:
    print(f"\n[ERROR] {message}\n")
    sys.exit(1)


async def connect(url, database: str):
    try:
        return await asyncpg.connect(
            host=url.host or "localhost", port=url.port or 5432,
            user=url.username, password=url.password, database=database,
        )
    except asyncpg.InvalidPasswordError:
        fail(f'Wrong password for PostgreSQL user "{url.username}".\n'
             "Fix DATABASE_URL in the .env file (project root). Special characters in the password must be\n"
             "URL-encoded: @ -> %40   : -> %3A   / -> %2F   # -> %23   % -> %25")
    except (OSError, asyncpg.CannotConnectNowError):
        fail(f"Cannot reach PostgreSQL at {url.host or 'localhost'}:{url.port or 5432}. Is the PostgreSQL service running?")
    except asyncpg.InvalidCatalogNameError:
        raise


async def ensure_database(url) -> None:
    name = url.database
    if not name or not re.fullmatch(r"[A-Za-z0-9_]+", name):
        fail(f'Database name "{name}" in DATABASE_URL must contain only letters, digits and "_".')
    conn = await connect(url, "postgres")
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists:
            print(f'Database "{name}" already exists.')
        else:
            await conn.execute(f'CREATE DATABASE "{name}"')
            print(f'Database "{name}" created.')
    except asyncpg.InsufficientPrivilegeError:
        fail(f'User "{url.username}" is not allowed to create databases. Use the "postgres" user or ask the admin.')
    finally:
        await conn.close()


def migrate() -> None:
    print("Applying migrations (alembic upgrade head) ...")
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND_DIR)
    if result.returncode != 0:
        fail("Migrations failed (see the message above).")


async def seed(url) -> None:
    if not SEED_FILE.exists():
        fail(f"Seed file not found: {SEED_FILE}")
    print("Loading demo data ...")
    conn = await connect(url, url.database)
    try:
        await conn.execute(SEED_FILE.read_text(encoding="utf-8"))
    finally:
        await conn.close()
    print("Demo accounts (password Demo1234): alice@example.com, bob@example.com, carol@example.com")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the database, apply migrations, optionally load demo data.")
    parser.add_argument("--seed", action="store_true", help="also load demo data from database/seed.sql")
    args = parser.parse_args()

    url = make_url(settings.DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        fail("DATABASE_URL must start with postgresql+asyncpg://")
    print(f"Using {url.render_as_string(hide_password=True)}")

    asyncio.run(ensure_database(url))
    migrate()
    if args.seed:
        asyncio.run(seed(url))
    print("\nDone. Start the API:  uvicorn app.main:app --reload --port 8000")


if __name__ == "__main__":
    main()
