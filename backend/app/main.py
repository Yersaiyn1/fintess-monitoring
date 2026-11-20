from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.middleware import ContextSetterMiddleware, DoctorAccessLogMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal

app = FastAPI(title="Fitness Monitoring API", version="0.1.0")

# Set context before any other middleware runs
app.add_middleware(ContextSetterMiddleware)
app.add_middleware(DoctorAccessLogMiddleware)
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


class AngularFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or Path(path).parts[:1] in {("api",), ("health",)}:
                raise
            accepts_html = any(
                name == b"accept" and b"text/html" in value
                for name, value in scope["headers"]
            )
            if not accepts_html or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


frontend_build = Path(__file__).resolve().parents[2] / "frontend/dist/fitness-monitoring/browser"
if (frontend_build / "index.html").is_file():
    app.mount("/", AngularFiles(directory=frontend_build, html=True), name="frontend")
