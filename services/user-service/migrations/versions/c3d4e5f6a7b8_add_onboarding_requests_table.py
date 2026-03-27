"""add onboarding_requests table for provider self-registration

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-23

Providers (doctor, lab, seller, pharmacy, groomer) submit an onboarding
form which creates a row here with status=pending. An admin then approves
or rejects it. On approval, the user account and tenant are created.
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onboarding_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portal_type", sa.String(30), nullable=False),
        sa.Column("mobile", sa.String(20), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("business_name", sa.String(255), nullable=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_onboarding_requests_mobile", "onboarding_requests", ["mobile"])
    op.create_index("ix_onboarding_requests_status", "onboarding_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_onboarding_requests_status", table_name="onboarding_requests")
    op.drop_index("ix_onboarding_requests_mobile", table_name="onboarding_requests")
    op.drop_table("onboarding_requests")
