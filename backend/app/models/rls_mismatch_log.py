"""Legacy SQLAlchemy model for the `rls_mismatch_log` table.

Retained solely for backwards compatibility with migration `0012_create_rls_mismatch_log.py`
and existing database schemas (non-destructive migration policy). The fake shadow RLS comparison
has been removed in Stage 1 in favor of Variant B (verified application-level authorization).
"""
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class RlsMismatchLog(Base):
    __tablename__ = "rls_mismatch_log"

    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    endpoint = Column(String(256), nullable=False)
    user_id = Column(Integer, nullable=True)
    doctor_id = Column(Integer, nullable=True)
    rows_mismatched = Column(Integer, nullable=False)
    details = Column(Text, nullable=True)
