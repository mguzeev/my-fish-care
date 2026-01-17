"""Add plan type and one-time purchase support.

Revision ID: b3c4d5e6f7g8
Revises: a1b2c3d4e5f6
Create Date: 2026-01-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7g8'
down_revision: str = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add plan_type column to subscription_plans (default: subscription)
    op.add_column('subscription_plans', 
        sa.Column('plan_type', sa.String(20), nullable=False, server_default='subscription'))
    
    # Add one_time_limit column to subscription_plans
    op.add_column('subscription_plans', 
        sa.Column('one_time_limit', sa.Integer(), nullable=True))
    
    # Add one_time_purchases_count column to billing_accounts (for tracking cumulative purchases)
    op.add_column('billing_accounts', 
        sa.Column('one_time_purchases_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove columns
    op.drop_column('billing_accounts', 'one_time_purchases_count')
    op.drop_column('subscription_plans', 'one_time_limit')
    op.drop_column('subscription_plans', 'plan_type')
