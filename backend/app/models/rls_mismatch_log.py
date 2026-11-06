"""SQLAlchemy model for RLS mismatch logging.

The table is created by migration 0012_create_rls_mismatch_log.py.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.db.session import AsyncSessionLocal
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

