"""Remember which permission expiry the patient has acknowledged."""
import sqlalchemy as sa
from alembic import op

revision = "0020_reminders"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("Doctor_Access", sa.Column("reminder_read_for", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("Doctor_Access", "reminder_read_for")
