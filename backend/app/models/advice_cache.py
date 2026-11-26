from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AdviceCache(Base):
    """Cached AI-phrased advice responses keyed by (user_id, lang)."""

    __tablename__ = "Advice_Cache"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), primary_key=True
    )
    lang: Mapped[str] = mapped_column(String(10), primary_key=True)
    metrics_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[list[dict]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
