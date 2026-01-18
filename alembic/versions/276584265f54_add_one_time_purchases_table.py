"""add_one_time_purchases_table

Revision ID: 276584265f54
Revises: 01ff044cdfea
Create Date: 2026-01-18 13:29:09.498803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '276584265f54'
down_revision: Union[str, None] = '01ff044cdfea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create one_time_purchases table
    op.create_table(
        'one_time_purchases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('billing_account_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=True),
        sa.Column('credits_purchased', sa.Integer(), nullable=False),
        sa.Column('price_paid', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), default='USD', nullable=False),
        sa.Column('paddle_transaction_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['billing_account_id'], ['billing_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='SET NULL'),
    )


def downgrade() -> None:
    op.drop_table('one_time_purchases')
