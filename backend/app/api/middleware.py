"""
Access logging middleware for doctor-facing endpoints.
Logs every doctor request to Access_Log table.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.session import AsyncSessionLocal
from app.models.access_log import AccessLog
import logging
import sqlalchemy as sa


logger = logging.getLogger(__name__)

DOCTOR_ENDPOINT_PREFIX = "/api/v1/doctor"


class ContextSetterMiddleware(BaseHTTPMiddleware):
    """Set session variables for user/doctor on each request.
    Works with any PgBouncer pool mode because we use `SET LOCAL` which
    applies only to the current transaction.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract IDs from custom headers (adjust as your auth mechanism).
        user_id = request.headers.get("x-user-id")
        doctor_id = request.headers.get("x-doctor-id")
        # Set context variables if PostgreSQL session is active
        try:
            async with AsyncSessionLocal() as session:
                if user_id:
                    await session.execute(sa.text(f"SET LOCAL app.current_user_id = '{int(user_id)}'"))
                if doctor_id:
                    await session.execute(sa.text(f"SET LOCAL app.current_doctor_id = '{int(doctor_id)}'"))
                await session.commit()
        except Exception as exc:
            logger.debug("Context setter skipped (e.g. SQLite test environment): %s", exc)
        response = await call_next(request)
        return response

class DoctorAccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only log doctor-facing endpoints
        if not request.url.path.startswith(DOCTOR_ENDPOINT_PREFIX):
            return response

        doctor_id_str = request.headers.get("x-doctor-id")
        user_id_str = request.headers.get("x-user-id")

        if not doctor_id_str or not user_id_str:
            return response

        try:
            doctor_id = int(doctor_id_str)
            user_id = int(user_id_str)
        except ValueError:
            return response

        result_str = "GRANTED" if response.status_code < 400 else "DENIED"

        try:
            async with AsyncSessionLocal() as session:
                log_entry = AccessLog(
                    doctor_id=doctor_id,
                    user_id=user_id,
                    endpoint=str(request.url.path),
                    result=result_str,
                )
                session.add(log_entry)
                await session.commit()
        except Exception as exc:
            logger.exception("Failed to write access log: %s", exc)

        return response
