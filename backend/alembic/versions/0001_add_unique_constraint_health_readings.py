"""Add UNIQUE INDEX CONCURRENTLY on Health_Readings(device_id, date_time)

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

PRODUCTION SAFETY:
- Uses CREATE UNIQUE INDEX CONCURRENTLY → no table lock, safe on live prod.
- CONCURRENTLY cannot run inside a transaction → migration uses autocommit block.
- Run ONLY after the deduplication script has been executed successfully.
- Run command:  alembic upgrade 0001

NO MAINTENANCE WINDOW REQUIRED.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

INDEX_NAME = "uq_health_readings_device_datetime"
TABLE_NAME = "Health_Readings"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(f"""
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
            ON "{TABLE_NAME}" (device_id, date_time)
        """))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(f"""
            DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}
        """))
