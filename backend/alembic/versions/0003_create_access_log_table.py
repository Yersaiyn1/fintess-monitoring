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
    op.create_table(
        'Access_Log',
        sa.Column('log_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('doctor_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column(
            'accessed_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('endpoint', sa.String(500), nullable=False),
        sa.Column('result', sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['Doctors.doctor_id'], name='fk_access_log_doctor'),
        sa.ForeignKeyConstraint(['user_id'], ['Users.user_id'], name='fk_access_log_user'),
        sa.PrimaryKeyConstraint('log_id', name='pk_access_log'),
    )
    
    # Create indexes on the new table (normal CREATE INDEX, no CONCURRENTLY needed for new table)
    op.create_index('idx_access_log_doctor_id', 'Access_Log', ['doctor_id'])
    op.create_index('idx_access_log_user_id', 'Access_Log', ['user_id'])
    op.create_index('idx_access_log_accessed_at', 'Access_Log', ['accessed_at'])


def downgrade() -> None:
    op.drop_index('idx_access_log_accessed_at', table_name='Access_Log')
    op.drop_index('idx_access_log_user_id', table_name='Access_Log')
    op.drop_index('idx_access_log_doctor_id', table_name='Access_Log')
    op.drop_table('Access_Log')
