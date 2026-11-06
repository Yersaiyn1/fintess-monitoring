from fastapi import APIRouter
from app.api.v1 import sync, doctor, dashboard

api_router = APIRouter()
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(doctor.router, prefix="/doctor", tags=["doctor"])
api_router.include_router(dashboard.router, prefix="", tags=["dashboard"])
