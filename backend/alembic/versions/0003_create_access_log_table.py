"""Create Access_Log table for doctor audit trail

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-01 00:02:00.000000

PRODUCTION SAFETY:
- CREATE TABLE is a DDL statement that only takes a brief ShareLock.
  On an empty (new) table this is instantaneous — effectively zero downtime.
- NO MAINTENANCE WINDOW REQUIRED.

Table structure:
  Access_Log(log_id SERIAL PK, doctor_id FK, user_id FK,
             accessed_at TIMESTAMPTZ DEFAULT now(),
             endpoint VARCHAR(500), result VARCHAR(50))
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS: the table may already exist when the database was created from database/schema.sql.
    op.execute("""
        CREATE TABLE IF NOT EXISTS "Access_Log" (
            log_id      SERIAL,
            doctor_id   INTEGER      NOT NULL,
            user_id     INTEGER      NOT NULL,
            accessed_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            endpoint    VARCHAR(500) NOT NULL,
            result      VARCHAR(50)  NOT NULL,
            CONSTRAINT pk_access_log PRIMARY KEY (log_id),
            CONSTRAINT fk_access_log_doctor FOREIGN KEY (doctor_id) REFERENCES "Doctors"(doctor_id),
            CONSTRAINT fk_access_log_user   FOREIGN KEY (user_id)   REFERENCES "Users"(user_id)
        )
    """)
    op.execute('CREATE INDEX IF NOT EXISTS idx_access_log_doctor_id   ON "Access_Log" (doctor_id)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_access_log_user_id     ON "Access_Log" (user_id)')
    op.execute('CREATE INDEX IF NOT EXISTS idx_access_log_accessed_at ON "Access_Log" (accessed_at)')


def downgrade() -> None:
    op.drop_index('idx_access_log_accessed_at', table_name='Access_Log')
    op.drop_index('idx_access_log_user_id', table_name='Access_Log')
    op.drop_index('idx_access_log_doctor_id', table_name='Access_Log')
    op.drop_table('Access_Log')
