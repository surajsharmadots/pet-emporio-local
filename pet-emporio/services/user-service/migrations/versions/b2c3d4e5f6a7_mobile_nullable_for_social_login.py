"""make users.mobile nullable for social login users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-23

Social login users (Google, Facebook, Apple) may not have a mobile number.
Making mobile nullable allows their accounts to be created without one.
PostgreSQL allows multiple NULLs in a unique constraint, so uniqueness is preserved.
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "mobile", existing_type=sa.String(20), nullable=True)


def downgrade() -> None:
    # Before reverting, ensure no NULL mobiles exist
    op.execute("DELETE FROM users WHERE mobile IS NULL")
    op.alter_column("users", "mobile", existing_type=sa.String(20), nullable=False)
