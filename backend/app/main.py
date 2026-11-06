from fastapi import FastAPI
from app.api.v1.router import api_router
from app.api.middleware import DoctorAccessLogMiddleware, ContextSetterMiddleware

app = FastAPI(title="Fitness Monitoring API", version="0.1.0")

# Set context before any other middleware runs
app.add_middleware(ContextSetterMiddleware)
app.add_middleware(DoctorAccessLogMiddleware)
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok"}
