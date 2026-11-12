from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Importing the package registers EVERY model on Base.metadata (used by Alembic and tests).
# To add a table: create app/models/<name>.py and add one line to app/models/__init__.py.
import app.models  # noqa: F401, E402
