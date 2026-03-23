"""gap_additions: first_name/last_name/is_profile_complete/is_walk_in on users,
is_active/deactivated_at/deactivated_reason on user_roles, commission_configs table

Revision ID: a1b2c3d4e5f6
Revises: 22ef8af70717
Create Date: 2026-03-18 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '22ef8af70717'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users table: GAP 1 + GAP 16 ─────────────────────────────────────────
    op.add_column('users', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('is_profile_complete', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('is_walk_in', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('created_by_provider_id', sa.String(length=36), nullable=True))

    # ── user_roles table: GAP 5 ──────────────────────────────────────────────
    op.add_column('user_roles', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('user_roles', sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_roles', sa.Column('deactivated_reason', sa.Text(), nullable=True))

    # ── commission_configs table: GAP 9 ──────────────────────────────────────
    op.create_table(
        'commission_configs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('scope', sa.String(length=20), nullable=False),
        sa.Column('tenant_type', sa.String(length=30), nullable=True),
        sa.Column('tenant_id', sa.String(length=36), nullable=True),
        sa.Column('commission_type', sa.String(length=10), nullable=False, server_default='percentage'),
        sa.Column('commission_value', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    # commission_configs
    op.drop_table('commission_configs')

    # user_roles
    op.drop_column('user_roles', 'deactivated_reason')
    op.drop_column('user_roles', 'deactivated_at')
    op.drop_column('user_roles', 'is_active')

    # users
    op.drop_column('users', 'created_by_provider_id')
    op.drop_column('users', 'is_walk_in')
    op.drop_column('users', 'is_profile_complete')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')