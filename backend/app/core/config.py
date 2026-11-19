"""Application settings.

Values are read from environment variables or from a `.env` file.
The `.env` file is searched in the repository root first and then in `backend/`,
so it works no matter from which folder uvicorn / alembic / pytest is started.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ROOT_DIR = _BACKEND_DIR.parent

INSECURE_SECRET_PREFIX = "change-me"
INSECURE_DB_PASSWORDS = frozenset({"change_me_please", "changeme"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ROOT_DIR / ".env", _BACKEND_DIR / ".env"),
        extra="ignore",
    )

    # Runtime connection string (should connect as least-privilege APP_DB_USER in production/Docker).
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fitness"

    # Optional migration/admin connection string (table owner role used by Alembic and setup_db.py).
    # Falls back to DATABASE_URL when not set so single-role local setups keep working.
    DATABASE_MIGRATION_URL: str | None = None

    # Optional runtime DB role credentials (used by scripts/configure_db_roles.py and migration 0021).
    APP_DB_USER: str = "app_user"
    APP_DB_PASSWORD: str | None = None

    # Secret used to sign JWT access tokens. MUST be changed in production.
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # "development" | "production"
    ENVIRONMENT: str = "development"

    # Comma-separated list of origins that may call the API from a browser.
    CORS_ORIGINS: str = "http://localhost:4200,http://127.0.0.1:4200"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def migration_database_url(self) -> str:
        return self.DATABASE_MIGRATION_URL or self.DATABASE_URL


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    if s.ENVIRONMENT == "production":
        if s.SECRET_KEY.startswith(INSECURE_SECRET_PREFIX) or len(s.SECRET_KEY) < 32:
            raise RuntimeError(
                "SECRET_KEY is insecure. Set a random value of at least 32 characters "
                '(e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`).'
            )
        if s.APP_DB_PASSWORD in INSECURE_DB_PASSWORDS or "change_me_please" in s.DATABASE_URL:
            raise RuntimeError(
                "Insecure database password 'change_me_please' is forbidden in production."
            )
    return s


settings = get_settings()
DATABASE_URL = settings.DATABASE_URL
