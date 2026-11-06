from sqlalchemy import Integer, String, Date
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class User(Base):
    __tablename__ = "Users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[object] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    registration_date: Mapped[object] = mapped_column(
        Date, server_default=func.current_date(), nullable=True
    )
