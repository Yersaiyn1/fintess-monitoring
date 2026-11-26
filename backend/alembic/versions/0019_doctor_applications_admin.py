"""Add admin roles and doctor applications.

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("Users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "Doctor_Applications",
        sa.Column("application_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("specialty", sa.String(255), nullable=False),
        sa.Column("license_number", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("documents", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("Users.user_id"), nullable=True),
        sa.Column("rejection_reason", sa.String(1000), nullable=True),
    )
    op.create_index(
        "uq_doctor_applications_pending_email",
        "Doctor_Applications", [sa.text("lower(email)")], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_doctor_applications_pending_license",
        "Doctor_Applications", [sa.text("lower(license_number)")], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_doctor_applications_pending_license", table_name="Doctor_Applications")
    op.drop_index("uq_doctor_applications_pending_email", table_name="Doctor_Applications")
    op.drop_table("Doctor_Applications")
    op.drop_column("Users", "is_admin")
