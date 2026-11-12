from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

_connect_args: dict = {}
if settings.DATABASE_URL.startswith("postgresql"):
    # Always work in UTC so "day" boundaries do not depend on the server's time zone.
    _connect_args["server_settings"] = {"timezone": "UTC"}

engine = create_async_engine(
    settings.DATABASE_URL, echo=False, pool_pre_ping=True, connect_args=_connect_args
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
