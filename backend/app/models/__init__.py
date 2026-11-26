"""Model registry.

Every SQLAlchemy model must be imported here, otherwise Alembic and the tests
will not see its table. One line per model, grouped by the phase that added it.
"""
# Baseline (before the phase-by-phase development)
from app.models.user import User  # noqa: F401
from app.models.doctor import Doctor  # noqa: F401
from app.models.device import Device  # noqa: F401
from app.models.health_reading import HealthReading  # noqa: F401
from app.models.sleep_session import SleepSession  # noqa: F401
from app.models.doctor_access import DoctorAccess  # noqa: F401
from app.models.access_log import AccessLog  # noqa: F401
from app.models.rls_mismatch_log import RlsMismatchLog  # noqa: F401

# Phase 2 — Activity Tracking
from app.models.workout import Workout  # noqa: F401

# Phase 3 — History & Analytics:    (no new tables; index added by migration 0017)
# Phase 4 — Goals & Settings:       (add goal / user_settings models here)
from app.models.user_goal import UserGoal  # noqa: F401
