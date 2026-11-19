from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal

app = FastAPI(title="Fitness Monitoring API", version="0.1.0")

# Added last = outermost, so CORS headers are present on every response (also on errors).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,  # JWT is sent in the Authorization header, not in cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health_check():
    """Liveness: the API process is running."""
    return {"status": "ok"}


@app.get("/health/db", tags=["health"])
async def health_db():
    """Readiness: the API can reach the database."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database is unavailable.")
    return {"status": "ok", "database": "up"}
