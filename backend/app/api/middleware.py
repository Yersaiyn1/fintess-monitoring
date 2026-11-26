"""
Access logging middleware for doctor-facing endpoints.
Logs every doctor request to Access_Log table.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.session import AsyncSessionLocal
from app.models.access_log import AccessLog
from app.core.security import decode_access_token
import logging


logger = logging.getLogger(__name__)

DOCTOR_ENDPOINT_PREFIX = "/api/v1/doctor"


class DoctorAccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only log doctor-facing endpoints
        if not request.url.path.startswith(DOCTOR_ENDPOINT_PREFIX):
            return response

        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return response
        try:
            doctor_id = decode_access_token(token, expected_role="doctor")
            path_parts = request.url.path.strip("/").split("/")
            user_id = int(path_parts[4]) if len(path_parts) == 6 and path_parts[:4] == ["api", "v1", "doctor", "patients"] and path_parts[5] == "readings" else None
        except (ValueError, IndexError):
            return response

        if doctor_id is None or user_id is None:
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
