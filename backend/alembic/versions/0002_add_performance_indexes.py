"""Add performance indexes (all CONCURRENTLY — no table locks)

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-01 00:01:00.000000

PRODUCTION SAFETY:
All three indexes are created with CONCURRENTLY — no table locks at any point.
NO MAINTENANCE WINDOW REQUIRED.

Indexes created:
1. idx_health_readings_device_datetime  — composite on (device_id, date_time)
   Used by: sync endpoint, time-range queries, doctor patient data retrieval.

2. idx_health_readings_hr_above_100     — partial on heart_rate_bpm WHERE > 100
   Used by: alert query "avg heart rate > 100 in last 7 days" (see README).
   Partial index → smaller, faster than full column index.

3. idx_doctor_access_doctor_end         — composite on (doctor_id, access_end)
   Used by: get_verified_doctor dependency (doctor_id + access_end > now()).
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        # 1. Composite index on Health_Readings(device_id, date_time)
        op.execute(sa.text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_readings_device_datetime
            ON "Health_Readings" (device_id, date_time)
        """))
        
        # 2. Partial index for high heart rate alert query
        op.execute(sa.text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_health_readings_hr_above_100
            ON "Health_Readings" (heart_rate_bpm)
            WHERE heart_rate_bpm > 100
        """))
        
        # 3. Composite index to accelerate doctor access verification
        op.execute(sa.text("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_doctor_access_doctor_end
            ON "Doctor_Access" (doctor_id, access_end)
        """))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_doctor_access_doctor_end"))
        op.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_health_readings_hr_above_100"))
        op.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_health_readings_device_datetime"))
