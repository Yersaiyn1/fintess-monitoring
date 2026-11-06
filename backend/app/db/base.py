from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic can see them
from app.models import user, device, health_reading, doctor, doctor_access, access_log  # noqa: F401, E402
