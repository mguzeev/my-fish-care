"""add_is_default_and_one_time_requests_used

Revision ID: 01ff044cdfea
Revises: d9645d75fbc5
Create Date: 2026-01-18 12:49:21.144736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01ff044cdfea'
down_revision: Union[str, None] = 'd9645d75fbc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_default to subscription_plans
    op.add_column('subscription_plans', sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'))
    
    # Add one_time_requests_used to billing_accounts
    op.add_column('billing_accounts', sa.Column('one_time_requests_used', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    # Remove added columns in reverse order
    op.drop_column('billing_accounts', 'one_time_requests_used')
    op.drop_column('subscription_plans', 'is_default')
